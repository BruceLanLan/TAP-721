// SPDX-License-Identifier: MIT
pragma solidity ^0.8.28;

import {ERC721Min} from "./vendor/ERC721Min.sol";
import {TapNetlistCheck} from "./vendor/TapNetlistCheck.sol";
import {TapCredentialCheck} from "./TapCredentialCheck.sol";
import {
    IERC5192,
    ITapCredential,
    ITapCredentialProven,
    ITapCredentialAttested,
    ITapCredentialClaimed
} from "./interfaces/ITapCredential.sol";

interface IERC1271 {
    function isValidSignature(bytes32 hash, bytes calldata signature) external view returns (bytes4);
}

/// @title Reference implementation of the TAP draft "Soulbound Netlist Credentials"
/// @notice Non-transferable TAP-721 tokens (metadata level L0, netlist bound at mint and recorded on chain) with
///         three issuance paths: proven (commit-reveal, on-chain exhaustive check), attested (EIP-712 attestation
///         redeemed by its recipient), claimed (self-issued). No owner, no upgrade path, no fees, no payout logic.
contract SoulboundNetlistCredential is
    ERC721Min,
    IERC5192,
    ITapCredential,
    ITapCredentialProven,
    ITapCredentialAttested,
    ITapCredentialClaimed
{
    // ------------------------------------------------------------------ constants

    uint8 internal constant KIND_PROVEN = 1;
    uint8 internal constant KIND_ATTESTED = 2;
    uint8 internal constant KIND_CLAIMED = 3;

    uint8 internal constant STATUS_NONE = 0;
    uint8 internal constant STATUS_ACTIVE = 1;
    uint8 internal constant STATUS_EXPIRED = 2;
    uint8 internal constant STATUS_REVOKED = 3;
    uint8 internal constant STATUS_SUPERSEDED = 4;

    /// Work bounds of a specification (§4.4 item 2), chosen from measurements so that the worst reveal stays below
    /// 12 million gas of execution, well inside a 16,777,216-gas transaction (EIP-7825):
    ///   gate work  = (max(1, 2^nIn / 256) + GATE_OVERHEAD) * maxGates <= MAX_GATE_WORK
    ///   table size = nOut * max(1, 2^nIn / 8)                         <= MAX_TABLE_BYTES
    /// One unit of gate work is one NAND evaluated on one 256-lane word; GATE_OVERHEAD charges the per-gate costs
    /// that do not depend on nIn (file check, design key, code storage of the file), each measured at about
    /// GATE_OVERHEAD units.
    uint256 public constant MAX_GATE_WORK = 1 << 16;
    uint256 public constant GATE_OVERHEAD = 20;
    uint256 public constant MAX_TABLE_BYTES = 1 << 17;
    uint256 public constant MAX_FILE_BYTES = 49_152;
    /// Delay between a rebind request and its completion, during which the old holder may veto (§4.7). A request
    /// that is not completed within REBIND_DELAY after it became ready lapses.
    uint64 public constant REBIND_DELAY = 7 days;

    bytes4 internal constant INTERFACE_ERC5192 = 0xb45a3c0e;
    uint256 internal constant HALF_N = 0x7fffffffffffffffffffffffffffffff5d576e7357a4501ddfe92f46681b20a0;
    /// Data bytes per code contract (EIP-170 limit 24,576 minus the leading STOP byte).
    uint256 internal constant CHUNK_SIZE = 24_575;

    bytes32 internal constant DOMAIN_TYPEHASH =
        keccak256("EIP712Domain(string name,string version,uint256 chainId,address verifyingContract)");
    bytes32 internal constant ATTESTATION_TYPEHASH = keccak256(
        "Attestation(address issuer,address recipient,uint8 subject,bytes32 scope,bytes32 artifact,bytes32 evidence,uint64 issuedAt,uint64 expiresAt,uint64 deadline,uint256 replaces,bytes32 nonce)"
    );
    bytes32 internal constant REBIND_TYPEHASH =
        keccak256("Rebind(address authority,uint256 oldTokenId,address newHolder,uint64 deadline,bytes32 nonce)");

    // ------------------------------------------------------------------ errors

    error Soulbound();
    error NotHolder();
    error BadSubject();
    error BadSpec(string why);
    error SpecExists();
    error UnknownSpec();
    error SeriesOverlap();
    error OutsideWindow();
    error CommitmentExists();
    error NoCommitment();
    error AlreadyHolds();
    error HasLatch();
    error PinMismatch();
    error TooManyGates();
    error WrongFunction();
    error DuplicateDesign(bytes32 earlierSpec);
    error FileTooLarge();
    error NotRecipient();
    error BadSignature();
    error OfferExpired();
    error AlreadyRedeemed();
    error AttestationIsRevoked();
    error BadAttestation(string why);
    error ArtifactNotStored();
    error BadReplaces();
    error NotIssuer();
    error NotRebindable();
    error NotAuthority();
    error NoPendingRebind();
    error RebindNotReady();
    error RebindLapsed();
    error BadQuery();
    error StoreFailed();
    error NotStored();

    // ------------------------------------------------------------------ storage

    struct StoredFile {
        address pointer; // data contract (chunks == 1) or chunk index contract (chunks > 1)
        uint32 size;
        uint16 chunks;
    }

    struct PendingRebind {
        address newHolder;
        uint64 readyAt;
    }

    string private _base;
    uint256 public nextTokenId = 1;

    mapping(uint256 => Credential) private _cred;
    mapping(uint256 => uint8) private _flag;
    mapping(address => uint256[]) private _held;
    mapping(bytes32 => StoredFile) private _files;

    mapping(bytes32 => Spec) private _specs;
    mapping(bytes32 => uint64) public seriesEnd;
    mapping(bytes32 => mapping(bytes32 => bytes32)) public seriesDesign;
    /// specId => committer => commitment => recorded (§4.5): commitments are kept per committer, so that copying
    /// a pending commit transaction cannot occupy the commitment of its sender.
    mapping(bytes32 => mapping(address => mapping(bytes32 => bool))) public committed;
    mapping(bytes32 => mapping(address => bool)) public holdsSpec;
    mapping(uint256 => PendingRebind) public pendingRebind;

    mapping(bytes32 => uint8) private _attState;
    mapping(bytes32 => uint256) private _attToken;
    mapping(bytes32 => bool) public rebindUsed;

    constructor(string memory name_, string memory symbol_, string memory baseURI_) ERC721Min(name_, symbol_) {
        _base = baseURI_;
    }

    // ------------------------------------------------------------------ ERC-165, ERC-5192, soulbinding

    /// @dev ERC-4906 (0x49064906) is not reported, although the vendored ERC721Min declares its events: the
    ///      metadata of a credential is fixed at mint (§3.2) and this contract never emits MetadataUpdate.
    function supportsInterface(bytes4 id) public view override returns (bool) {
        if (id == 0x49064906) return false;
        return id == INTERFACE_ERC5192 || id == type(ITapCredential).interfaceId
            || id == type(ITapCredentialProven).interfaceId || id == type(ITapCredentialAttested).interfaceId
            || id == type(ITapCredentialClaimed).interfaceId || super.supportsInterface(id);
    }

    function locked(uint256 tokenId) external view returns (bool) {
        _requireOwned(tokenId);
        return true;
    }

    function transferFrom(address, address, uint256) public pure override {
        revert Soulbound();
    }

    function approve(address, uint256) public pure override {
        revert Soulbound();
    }

    function setApprovalForAll(address, bool) public pure override {
        revert Soulbound();
    }

    /// @dev The base URI is fixed at deployment: the metadata of a token cannot be changed by this contract (§3.2).
    function tokenURI(uint256 tokenId) public view override returns (string memory) {
        _requireOwned(tokenId);
        return string.concat(_base, _decimal(tokenId));
    }

    // ------------------------------------------------------------------ core reads

    function credentialOf(uint256 tokenId) external view returns (Credential memory) {
        _requireOwned(tokenId);
        return _cred[tokenId];
    }

    function statusOf(uint256 tokenId) public view returns (uint8) {
        if (_ownerOf(tokenId) == address(0)) return STATUS_NONE;
        uint8 f = _flag[tokenId];
        if (f != STATUS_ACTIVE) return f;
        uint64 e = _cred[tokenId].expiresAt;
        return (e != 0 && block.timestamp >= e) ? STATUS_EXPIRED : STATUS_ACTIVE;
    }

    function credentialsOf(
        address holder,
        uint8 kind,
        address issuer,
        bytes32 scope,
        bool activeOnly,
        uint256 cursor,
        uint256 limit
    ) external view returns (uint256[] memory tokenIds, uint256 nextCursor) {
        if (kind == 0 || kind > KIND_CLAIMED || limit == 0) revert BadQuery();
        uint256[] storage list = _held[holder];
        uint256 n = list.length;
        uint256 room = cursor < n ? n - cursor : 0;
        tokenIds = new uint256[](limit < room ? limit : room);
        uint256 found;
        uint256 i = cursor;
        while (i < n && found < limit) {
            uint256 t = list[i++];
            if (_ownerOf(t) != holder) continue;
            Credential storage c = _cred[t];
            if (c.kind != kind) continue;
            if (issuer != address(0) && c.issuer != issuer) continue;
            if (scope != bytes32(0) && c.scope != scope) continue;
            if (activeOnly && statusOf(t) != STATUS_ACTIVE) continue;
            tokenIds[found++] = t;
        }
        assembly ("memory-safe") {
            mstore(tokenIds, found)
        }
        nextCursor = i < n ? i : 0;
    }

    function netlistHashOf(uint256 tokenId) external view returns (bytes32) {
        _requireOwned(tokenId);
        return _cred[tokenId].artifact;
    }

    function netlistFile(bytes32 netlistHash) public view returns (bytes memory file) {
        StoredFile memory s = _files[netlistHash];
        if (s.pointer == address(0)) revert NotStored();
        file = new bytes(s.size);
        address pointer = s.pointer;
        if (s.chunks == 1) {
            assembly ("memory-safe") {
                extcodecopy(pointer, add(file, 0x20), 1, mload(file))
            }
        } else {
            uint256 chunks = s.chunks;
            bytes memory index = new bytes(20 * chunks);
            assembly ("memory-safe") {
                extcodecopy(pointer, add(index, 0x20), 1, mload(index))
                let dst := add(file, 0x20)
                for { let i := 0 } lt(i, chunks) { i := add(i, 1) } {
                    let chunk := shr(96, mload(add(add(index, 0x20), mul(i, 20))))
                    let len := sub(extcodesize(chunk), 1)
                    extcodecopy(chunk, dst, 1, len)
                    dst := add(dst, len)
                }
            }
        }
    }

    function storeNetlist(bytes calldata file) external returns (bytes32) {
        if (file.length > MAX_FILE_BYTES) revert FileTooLarge();
        TapNetlistCheck.check(file);
        return _store(file);
    }

    function renounce(uint256 tokenId) external {
        if (_ownerOf(tokenId) != msg.sender) revert NotHolder();
        delete pendingRebind[tokenId]; // §4.7: renouncing ends a pending rebind of the token
        _burn(tokenId);
        emit CredentialStatusChanged(tokenId, STATUS_NONE);
    }

    // ------------------------------------------------------------------ proven

    function registerSpec(Spec calldata s) external returns (bytes32 id) {
        if (s.registrant != msg.sender) revert BadSpec("registrant");
        if (s.nOut == 0 || s.nOut > 1 << 16 || s.nIn > 16) revert BadSpec("pins");
        if (s.target == bytes32(0)) revert BadSpec("target");
        if (s.maxGates < s.nOut) revert BadSpec("maxGates");
        if (!(s.commitStart < s.commitEnd && s.commitEnd < s.revealEnd)) revert BadSpec("windows");
        if (s.unique && s.series == bytes32(0)) revert BadSpec("unique without series");
        if (gateWork(s.nIn, s.maxGates) > MAX_GATE_WORK) revert BadSpec("gate work");
        if (tableBytes(s.nIn, s.nOut) > MAX_TABLE_BYTES) revert BadSpec("table size");
        id = specId(s);
        if (_specs[id].registrant != address(0)) revert SpecExists();
        if (s.series != bytes32(0)) {
            bytes32 sk = seriesKey(s.registrant, s.series);
            if (s.commitStart < seriesEnd[sk]) revert SeriesOverlap();
            seriesEnd[sk] = s.revealEnd;
        }
        _specs[id] = s;
        emit SpecRegistered(id, s.registrant);
    }

    function specOf(bytes32 id) external view returns (Spec memory s, uint256 maxGateWork, uint256 maxTableBytes) {
        s = _specs[id];
        if (s.registrant == address(0)) revert UnknownSpec();
        return (s, MAX_GATE_WORK, MAX_TABLE_BYTES);
    }

    function checkBounds() external pure returns (uint256 maxGateWork, uint256 maxTableBytes) {
        return (MAX_GATE_WORK, MAX_TABLE_BYTES);
    }

    function gateWork(uint256 nIn, uint256 maxGates) public pure returns (uint256) {
        return ((nIn >= 8 ? 1 << (nIn - 8) : 1) + GATE_OVERHEAD) * maxGates;
    }

    function tableBytes(uint256 nIn, uint256 nOut) public pure returns (uint256) {
        return nOut * (nIn >= 3 ? 1 << (nIn - 3) : 1);
    }

    function commit(bytes32 id, bytes32 commitment) external {
        Spec storage s = _specs[id];
        if (s.registrant == address(0)) revert UnknownSpec();
        if (block.timestamp < s.commitStart || block.timestamp >= s.commitEnd) revert OutsideWindow();
        if (committed[id][msg.sender][commitment]) revert CommitmentExists();
        committed[id][msg.sender][commitment] = true;
        emit Committed(id, msg.sender, commitment);
    }

    function reveal(bytes32 id, address recipient, uint8 subject, bytes calldata file, bytes32 salt)
        external
        returns (uint256 t)
    {
        Spec memory s = _specs[id];
        if (s.registrant == address(0)) revert UnknownSpec();
        if (block.timestamp < s.commitEnd || block.timestamp >= s.revealEnd) revert OutsideWindow();
        if (subject > 1) revert BadSubject();
        bytes32 nh = sha256(file);
        bytes32 c = commitmentOf(id, recipient, subject, nh, salt);
        if (!committed[id][recipient][c]) revert NoCommitment();
        if (holdsSpec[id][recipient]) revert AlreadyHolds();
        bytes32 dk = _checkSubmission(s, id, file);
        delete committed[id][recipient][c];
        if (s.series != bytes32(0)) {
            // §4.6: every reveal of a series records its design key, so that a later unique round sees it
            bytes32 sk = seriesKey(s.registrant, s.series);
            if (seriesDesign[sk][dk] == bytes32(0)) seriesDesign[sk][dk] = id;
        }
        _store(file);
        holdsSpec[id][recipient] = true;
        t = _mintCredential(
            recipient,
            Credential(KIND_PROVEN, subject, s.registrant, id, nh, bytes32(0), uint64(block.timestamp), 0, 0)
        );
        emit Accepted(t, id, recipient, nh, dk);
    }

    function requestRebind(Rebind calldata r, bytes calldata sig) external returns (uint64 readyAt) {
        if (msg.sender != r.newHolder) revert NotRecipient();
        uint256 old = r.oldTokenId;
        if (_ownerOf(old) == address(0) || _cred[old].kind != KIND_PROVEN) revert NotRebindable();
        if (_flag[old] == STATUS_SUPERSEDED) revert NotRebindable();
        bytes32 sid = _cred[old].scope;
        address auth = _specs[sid].recoveryAuthority;
        if (auth == address(0) || r.authority != auth) revert NotAuthority();
        if (r.deadline != 0 && block.timestamp > r.deadline) revert OfferExpired();
        if (holdsSpec[sid][r.newHolder]) revert AlreadyHolds();
        bytes32 h = rebindDigest(r);
        if (rebindUsed[h] || !_validSig(auth, h, sig)) revert BadSignature();
        rebindUsed[h] = true;
        readyAt = uint64(block.timestamp) + REBIND_DELAY;
        // a new request replaces a pending or lapsed one and restarts the delay (§4.7)
        pendingRebind[old] = PendingRebind(r.newHolder, readyAt);
        emit RebindRequested(old, r.newHolder, readyAt);
    }

    function vetoRebind(uint256 old) external {
        if (_ownerOf(old) != msg.sender) revert NotHolder();
        if (!_isPending(old)) revert NoPendingRebind();
        delete pendingRebind[old];
        emit RebindVetoed(old);
    }

    function completeRebind(uint256 old) external returns (uint256 t) {
        PendingRebind memory p = pendingRebind[old];
        if (p.newHolder == address(0)) revert NoPendingRebind();
        if (msg.sender != p.newHolder) revert NotRecipient();
        if (block.timestamp < p.readyAt) revert RebindNotReady();
        if (block.timestamp >= uint256(p.readyAt) + REBIND_DELAY) revert RebindLapsed();
        if (_ownerOf(old) == address(0) || _flag[old] == STATUS_SUPERSEDED) revert NotRebindable();
        Credential memory c = _cred[old];
        if (holdsSpec[c.scope][p.newHolder]) revert AlreadyHolds();
        delete pendingRebind[old];
        holdsSpec[c.scope][p.newHolder] = true;
        c.issuedAt = uint64(block.timestamp);
        c.replaces = old;
        _setFlag(old, STATUS_SUPERSEDED);
        t = _mintCredential(p.newHolder, c);
        emit CredentialRebound(old, t);
    }

    // ------------------------------------------------------------------ attested

    function redeem(Attestation calldata a, bytes calldata sig) external returns (uint256 t) {
        if (a.issuer == address(0) || a.recipient == address(0)) revert BadAttestation("address");
        if (a.subject > 1) revert BadAttestation("subject");
        if (a.artifact == bytes32(0) || a.scope == bytes32(0)) revert BadAttestation("artifact or scope");
        if (a.expiresAt != 0 && a.expiresAt <= a.issuedAt) revert BadAttestation("expiry");
        if (a.issuedAt > block.timestamp) revert BadAttestation("issued in the future");
        if (a.expiresAt != 0 && a.expiresAt <= block.timestamp) revert BadAttestation("expired");
        if (msg.sender != a.recipient) revert NotRecipient();
        bytes32 h = attestationDigest(a);
        if (_attState[h] == 1) revert AlreadyRedeemed();
        if (_attState[h] == 2) revert AttestationIsRevoked();
        if (a.deadline != 0 && block.timestamp > a.deadline) revert OfferExpired();
        if (!_validSig(a.issuer, h, sig)) revert BadSignature();
        if (_files[a.artifact].pointer == address(0)) revert ArtifactNotStored();
        if (a.replaces != 0) {
            uint256 old = a.replaces;
            if (_ownerOf(old) == address(0) || _cred[old].kind != KIND_ATTESTED || _cred[old].issuer != a.issuer) {
                revert BadReplaces();
            }
            uint8 st = _flag[old];
            if (st == STATUS_SUPERSEDED || st == STATUS_REVOKED) revert NotRebindable();
        }
        _attState[h] = 1;
        t = _mintCredential(
            a.recipient,
            Credential(
                KIND_ATTESTED, a.subject, a.issuer, a.scope, a.artifact, a.evidence, a.issuedAt, a.expiresAt, a.replaces
            )
        );
        _attToken[h] = t;
        if (a.replaces != 0) {
            _setFlag(a.replaces, STATUS_SUPERSEDED);
            emit CredentialRebound(a.replaces, t);
        }
    }

    function revokeAttestation(Attestation calldata a) external {
        if (msg.sender != a.issuer) revert NotIssuer();
        bytes32 h = attestationDigest(a);
        if (_attState[h] == 2) return;
        _attState[h] = 2;
        emit AttestationRevoked(h, a.issuer);
        uint256 t = _attToken[h];
        if (t != 0 && _ownerOf(t) != address(0) && _flag[t] == STATUS_ACTIVE) _setFlag(t, STATUS_REVOKED);
    }

    function attestationStatus(bytes32 id) external view returns (uint8, uint256) {
        return (_attState[id], _attToken[id]);
    }

    // ------------------------------------------------------------------ claimed

    function claim(bytes calldata file, bytes32 statementId, bytes32 evidence, uint8 subject)
        external
        returns (uint256)
    {
        if (subject > 1) revert BadSubject();
        if (file.length > MAX_FILE_BYTES) revert FileTooLarge();
        TapNetlistCheck.check(file);
        bytes32 nh = _store(file);
        return _mintCredential(
            msg.sender,
            Credential(
                KIND_CLAIMED,
                subject,
                msg.sender,
                claimScope(statementId),
                nh,
                evidence,
                uint64(block.timestamp),
                0,
                0
            )
        );
    }

    // ------------------------------------------------------------------ hashing (public for tools and tests)

    function specId(Spec calldata s) public pure returns (bytes32) {
        bytes memory a =
            abi.encodePacked("tap-credential-spec/1\x00", s.registrant, s.nIn, s.nOut, s.target, s.maxGates, s.unique);
        bytes memory b = abi.encodePacked(
            s.series, s.commitStart, s.commitEnd, s.revealEnd, s.recoveryAuthority, s.infoHash
        );
        return sha256(bytes.concat(a, b));
    }

    function seriesKey(address registrant, bytes32 series) public pure returns (bytes32) {
        return sha256(abi.encodePacked("tap-credential-series/1\x00", registrant, series));
    }

    function commitmentOf(bytes32 id, address recipient, uint8 subject, bytes32 netlistHash, bytes32 salt)
        public
        pure
        returns (bytes32)
    {
        return sha256(abi.encodePacked("tap-credential-commit/1\x00", id, recipient, subject, netlistHash, salt));
    }

    /// @notice The scope of a claimed credential (§6): zero, or a domain-separated hash of the statement id.
    function claimScope(bytes32 statementId) public pure returns (bytes32) {
        if (statementId == bytes32(0)) return bytes32(0);
        return sha256(abi.encodePacked("tap-credential-claim/1\x00", statementId));
    }

    function domainSeparator() public view returns (bytes32) {
        return keccak256(
            abi.encode(
                DOMAIN_TYPEHASH,
                keccak256("TAP Soulbound Credentials"),
                keccak256("1"),
                block.chainid,
                address(this)
            )
        );
    }

    function attestationDigest(Attestation calldata a) public view returns (bytes32) {
        bytes32 sh = keccak256(
            abi.encode(
                ATTESTATION_TYPEHASH,
                a.issuer,
                a.recipient,
                a.subject,
                a.scope,
                a.artifact,
                a.evidence,
                a.issuedAt,
                a.expiresAt,
                a.deadline,
                a.replaces,
                a.nonce
            )
        );
        return keccak256(abi.encodePacked("\x19\x01", domainSeparator(), sh));
    }

    function rebindDigest(Rebind calldata r) public view returns (bytes32) {
        bytes32 sh =
            keccak256(abi.encode(REBIND_TYPEHASH, r.authority, r.oldTokenId, r.newHolder, r.deadline, r.nonce));
        return keccak256(abi.encodePacked("\x19\x01", domainSeparator(), sh));
    }

    /// @notice The checks of §4.6 items 4-7 without state: returns (designKey, truthTableHash or 0).
    function inspect(bytes calldata file) external view returns (bytes32 dk, bytes32 tt) {
        bytes memory f = file;
        (uint256 nIn, uint256 nOut, uint256 nand, uint256 latch) = TapNetlistCheck.check(f);
        if (latch != 0) revert HasLatch();
        dk = TapCredentialCheck.designKey(f, nIn, nOut, nand);
        if (nIn <= 16) tt = TapCredentialCheck.truthTableHash(f, nIn, nOut, nand);
    }

    // ------------------------------------------------------------------ internal

    /// @dev §4.6 items 4-8: file, pins, gate budget, function, duplicate design (unique).
    function _checkSubmission(Spec memory s, bytes32 id, bytes calldata file) internal view returns (bytes32 dk) {
        if (file.length > MAX_FILE_BYTES) revert FileTooLarge();
        bytes memory f = file;
        (uint256 nIn, uint256 nOut, uint256 nand, uint256 latch) = TapNetlistCheck.check(f);
        if (latch != 0) revert HasLatch();
        if (nIn != s.nIn || nOut != s.nOut) revert PinMismatch();
        if (nand > s.maxGates) revert TooManyGates();
        dk = TapCredentialCheck.designKey(f, nIn, nOut, nand);
        if (TapCredentialCheck.truthTableHash(f, nIn, nOut, nand) != s.target) revert WrongFunction();
        if (s.unique) {
            bytes32 prior = seriesDesign[seriesKey(s.registrant, s.series)][dk];
            if (prior != bytes32(0) && prior != id) revert DuplicateDesign(prior);
        }
    }

    function _mintCredential(address to, Credential memory c) internal returns (uint256 t) {
        t = nextTokenId++;
        _cred[t] = c;
        _flag[t] = STATUS_ACTIVE;
        _held[to].push(t);
        _mint(to, t);
        emit Locked(t);
        emit CredentialIssued(t, to, c.kind, c.subject, c.issuer, c.scope, c.artifact);
    }

    function _setFlag(uint256 t, uint8 status) internal {
        _flag[t] = status;
        emit CredentialStatusChanged(t, status);
    }

    /// @dev §4.7: a request is pending from its RebindRequested until it is completed, vetoed, replaced, ended by a
    ///      renounce, or lapses REBIND_DELAY after it became ready.
    function _isPending(uint256 old) internal view returns (bool) {
        PendingRebind memory p = pendingRebind[old];
        return p.newHolder != address(0) && block.timestamp < uint256(p.readyAt) + REBIND_DELAY;
    }

    /// @dev SSTORE2-style code storage, as in the TAP-721 reference store: runtime code 0x00 (STOP) ‖ data;
    ///      files above CHUNK_SIZE bytes are split, and the pointer is an index of the chunk addresses.
    function _store(bytes calldata file) internal returns (bytes32 h) {
        h = sha256(file);
        if (_files[h].pointer != address(0)) return h;
        uint256 size = file.length;
        uint256 chunks = (size + CHUNK_SIZE - 1) / CHUNK_SIZE;
        uint256 offset;
        assembly ("memory-safe") {
            offset := file.offset
        }
        address pointer;
        if (chunks == 1) {
            pointer = _deployFromCalldata(offset, size);
        } else {
            bytes memory index = new bytes(20 * chunks);
            for (uint256 i; i < chunks; ++i) {
                uint256 start = i * CHUNK_SIZE;
                uint256 len = size - start < CHUNK_SIZE ? size - start : CHUNK_SIZE;
                address chunk = _deployFromCalldata(offset + start, len);
                assembly ("memory-safe") {
                    mstore(add(add(index, 0x20), mul(i, 20)), shl(96, chunk))
                }
            }
            pointer = _deployFromMemory(index);
        }
        _files[h] = StoredFile(pointer, uint32(size), uint16(chunks));
    }

    /// @dev 10-byte init code `61 <size:2> 80 60 0a 3d 39 3d f3` followed by the runtime 0x00 ‖ data.
    function _deployFromCalldata(uint256 offset, uint256 len) internal returns (address pointer) {
        assembly ("memory-safe") {
            let p := mload(0x40)
            mstore(p, shl(168, or(or(shl(80, 0x61), shl(64, add(len, 1))), 0x80600a3d393df300)))
            calldatacopy(add(p, 11), offset, len)
            pointer := create(0, p, add(len, 11))
        }
        if (pointer == address(0)) revert StoreFailed();
    }

    function _deployFromMemory(bytes memory data) internal returns (address pointer) {
        assembly ("memory-safe") {
            let len := mload(data)
            let p := mload(0x40)
            mstore(p, shl(168, or(or(shl(80, 0x61), shl(64, add(len, 1))), 0x80600a3d393df300)))
            pop(staticcall(gas(), 0x04, add(data, 0x20), len, add(p, 11), len))
            pointer := create(0, p, add(len, 11))
        }
        if (pointer == address(0)) revert StoreFailed();
    }

    /// @dev §5.3: a 65-byte signature that recovers to the signer is accepted first, whether or not the signer
    ///      has code (an EIP-7702 account keeps its key); otherwise a signer with code is asked under ERC-1271.
    function _validSig(address signer, bytes32 h, bytes calldata sig) internal view returns (bool) {
        if (sig.length == 65) {
            bytes32 r = bytes32(sig[0:32]);
            bytes32 s = bytes32(sig[32:64]);
            uint8 v = uint8(sig[64]);
            if (v < 27) v += 27;
            if ((v == 27 || v == 28) && uint256(s) <= HALF_N && r != 0 && s != 0) {
                address got = ecrecover(h, v, r, s);
                if (got != address(0) && got == signer) return true;
            }
        }
        if (signer.code.length != 0) {
            (bool ok, bytes memory ret) = signer.staticcall(abi.encodeCall(IERC1271.isValidSignature, (h, sig)));
            return ok && ret.length >= 32 && bytes4(ret) == IERC1271.isValidSignature.selector;
        }
        return false;
    }

    function _decimal(uint256 v) internal pure returns (string memory) {
        if (v == 0) return "0";
        uint256 len;
        for (uint256 x = v; x != 0; x /= 10) len++;
        bytes memory b = new bytes(len);
        for (; v != 0; v /= 10) b[--len] = bytes1(uint8(48 + v % 10));
        return string(b);
    }
}
