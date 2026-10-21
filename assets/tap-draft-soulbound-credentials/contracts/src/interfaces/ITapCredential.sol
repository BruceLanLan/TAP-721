// SPDX-License-Identifier: CC0-1.0
pragma solidity ^0.8.28;

/// @notice ERC-5192: Minimal Soulbound NFTs (ERC-165 id 0xb45a3c0e).
interface IERC5192 {
    event Locked(uint256 tokenId);
    event Unlocked(uint256 tokenId);

    function locked(uint256 tokenId) external view returns (bool);
}

/// @title Soulbound netlist credentials, core interface (TAP draft "Soulbound Netlist Credentials" §8.1)
interface ITapCredential {
    /// kind: 1 proven, 2 attested, 3 claimed. subject: 0 account, 1 agent.
    struct Credential {
        uint8 kind;
        uint8 subject;
        address issuer;
        bytes32 scope;
        bytes32 artifact;
        bytes32 evidence;
        uint64 issuedAt;
        uint64 expiresAt;
        uint256 replaces;
    }

    /// status: 0 none, 1 active, 2 expired, 3 revoked, 4 superseded
    function credentialOf(uint256 tokenId) external view returns (Credential memory);
    function statusOf(uint256 tokenId) external view returns (uint8);
    /// kind MUST NOT be 0; limit MUST be at least 1
    function credentialsOf(
        address holder,
        uint8 kind,
        address issuer,
        bytes32 scope,
        bool activeOnly,
        uint256 cursor,
        uint256 limit
    ) external view returns (uint256[] memory tokenIds, uint256 nextCursor);
    function netlistHashOf(uint256 tokenId) external view returns (bytes32);
    function netlistFile(bytes32 netlistHash) external view returns (bytes memory);
    function storeNetlist(bytes calldata file) external returns (bytes32 netlistHash);
    function renounce(uint256 tokenId) external;

    event CredentialIssued(
        uint256 indexed tokenId,
        address indexed holder,
        uint8 indexed kind,
        uint8 subject,
        address issuer,
        bytes32 scope,
        bytes32 artifact
    );
    event CredentialStatusChanged(uint256 indexed tokenId, uint8 status);
    event CredentialRebound(uint256 indexed oldTokenId, uint256 indexed newTokenId);
}

/// @title Proven issuance (§8.2): exhaustive checks only in version 1
interface ITapCredentialProven {
    struct Spec {
        address registrant;
        uint32 nIn;
        uint32 nOut;
        bytes32 target;
        uint32 maxGates;
        bool unique;
        bytes32 series;
        uint64 commitStart;
        uint64 commitEnd;
        uint64 revealEnd;
        address recoveryAuthority;
        bytes32 infoHash;
    }

    struct Rebind {
        address authority;
        uint256 oldTokenId;
        address newHolder;
        uint64 deadline;
        bytes32 nonce;
    }

    function registerSpec(Spec calldata spec) external returns (bytes32 specId);
    function specOf(bytes32 specId)
        external
        view
        returns (Spec memory spec, uint256 maxGateWork, uint256 maxTableBytes);
    function checkBounds() external view returns (uint256 maxGateWork, uint256 maxTableBytes);
    function commit(bytes32 specId, bytes32 commitment) external;
    function reveal(bytes32 specId, address recipient, uint8 subject, bytes calldata file, bytes32 salt)
        external
        returns (uint256 tokenId);
    function requestRebind(Rebind calldata request, bytes calldata signature) external returns (uint64 readyAt);
    function vetoRebind(uint256 oldTokenId) external;
    function completeRebind(uint256 oldTokenId) external returns (uint256 tokenId);

    event SpecRegistered(bytes32 indexed specId, address indexed registrant);
    event Committed(bytes32 indexed specId, address indexed committer, bytes32 commitment);
    event Accepted(
        uint256 indexed tokenId, bytes32 indexed specId, address indexed recipient, bytes32 netlistHash, bytes32 designKey
    );
    event RebindRequested(uint256 indexed oldTokenId, address indexed newHolder, uint64 readyAt);
    event RebindVetoed(uint256 indexed oldTokenId);
}

/// @title Attested issuance (§8.3)
interface ITapCredentialAttested {
    struct Attestation {
        address issuer;
        address recipient;
        uint8 subject;
        bytes32 scope;
        bytes32 artifact;
        bytes32 evidence;
        uint64 issuedAt;
        uint64 expiresAt;
        uint64 deadline;
        uint256 replaces;
        bytes32 nonce;
    }

    function redeem(Attestation calldata attestation, bytes calldata signature) external returns (uint256 tokenId);
    function revokeAttestation(Attestation calldata attestation) external;
    /// state: 0 unknown, 1 redeemed, 2 revoked
    function attestationStatus(bytes32 attestationId) external view returns (uint8 state, uint256 tokenId);

    event AttestationRevoked(bytes32 indexed attestationId, address indexed issuer);
}

/// @title Claimed issuance (§8.4)
interface ITapCredentialClaimed {
    function claim(bytes calldata file, bytes32 statementId, bytes32 evidence, uint8 subject)
        external
        returns (uint256 tokenId);
}
