"""
Developer Utility for Signing BioPro Plugins.

Commands:
    init:       Generate a new Ed25519 developer key pair.
    sign:       Calculate integrity hashes and sign a plugin manual.
    registry:   Export the JSON snippet for the central registry.
"""

import sys
import os
import json
import hashlib
import logging
from pathlib import Path
from dataclasses import dataclass
from cryptography.hazmat.primitives.asymmetric import ed25519
from cryptography.hazmat.primitives import serialization
from typing import List, Optional

@dataclass
class TrustLink:
    """A single link in the trust chain (Issuer -> Subject)."""
    subject_name: str
    subject_pub: str # Hex encoded Ed25519 public key
    issuer_name: str
    signature: str   # Hex encoded signature
    
    def to_dict(self) -> dict:
        return {
            "subject_name": self.subject_name,
            "subject_pub": self.subject_pub,
            "issuer_name": self.issuer_name,
            "signature": self.signature
        }

@dataclass
class TrustChain:
    """The full chain of trust for a plugin."""
    links: List[TrustLink]
    
    def to_json(self) -> str:
        return json.dumps([link.to_dict() for link in self.links], indent=4)
    
    @classmethod
    def from_json(cls, json_str: str) -> 'TrustChain':
        data = json.loads(json_str)
        links = [TrustLink(**item) for item in data]
        return cls(links=links)
    
    @classmethod
    def from_file(cls, path: Path) -> Optional['TrustChain']:
        if not path.exists():
            return None
        try:
            with open(path, "r") as f:
                return cls.from_json(f.read())
        except Exception:
            return None

# Configure basic logging for CLI
logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger("biopro-signer")

MANDATORY_EXTENSIONS = {".py", ".pyw", ".json", ".yml", ".yaml", ".fcs"}
IGNORE_LIST = {
    ".DS_Store", "Thumbs.db", "__pycache__", 
    ".git", ".github", ".vscode", ".idea", ".pytest_cache",
    "cache", "results", "temp", "logs", "output", "dist", "build",
    "signature.bin", "trust_chain.json", "manifest.json", "dev_cert.bin"
}

class PluginSigner:
    def __init__(self):
        self.dev_dir = Path.home() / ".biopro" / "dev_keys"
        self.private_key_path = self.dev_dir / "private.key"
        self.public_key_path = self.dev_dir / "public.pub"
        self.delegation_path = self.dev_dir / "delegation.json" # Your credentials from authority

    def init_identity(self):
        """Generates a new Ed25519 identity."""
        if self.private_key_path.exists():
            logger.error("Identity already exists. Delete ~/.biopro/dev_keys/ to regenerate.")
            return

        self.dev_dir.mkdir(parents=True, exist_ok=True)
        private_key = ed25519.Ed25519PrivateKey.generate()
        public_key = private_key.public_key()

        # Save Private Key (PKCS8)
        with open(self.private_key_path, "wb") as f:
            f.write(private_key.private_bytes(
                encoding=serialization.Encoding.PEM,
                format=serialization.PrivateFormat.PKCS8,
                encryption_algorithm=serialization.NoEncryption()
            ))

        # Save Public Key (Raw Bytes for the Registry)
        with open(self.public_key_path, "wb") as f:
            f.write(public_key.public_bytes(
                encoding=serialization.Encoding.Raw,
                format=serialization.PublicFormat.Raw
            ))

        logger.info(f"Identity generated successfully.")
        logger.info(f"Private Key: {self.private_key_path}")
        logger.info(f"Public Key:  {self.public_key_path}")
        logger.warning("Keep your private.key SAFE and SECRET!")

    def load_private_key(self) -> ed25519.Ed25519PrivateKey:
        if not self.private_key_path.exists():
            raise FileNotFoundError("Developer identity not found. Run 'init' first.")
        with open(self.private_key_path, "rb") as f:
            return serialization.load_pem_private_key(f.read(), password=None)

    def sign_plugin(self, plugin_path: Path):
        """Updates manifest.json with hashes and creates signature.bin & dev_cert.bin."""
        private_key = self.load_private_key()
        public_key = private_key.public_key()
        
        manifest_file = plugin_path / "manifest.json"
        if not manifest_file.exists():
            logger.error(f"manifest.json not found in {plugin_path}")
            return

        with open(manifest_file, "r") as f:
            manifest = json.load(f)

        plugin_id = manifest.get("id")
        if not plugin_id or plugin_id != plugin_path.name:
            logger.error("Plugin ID in manifest must match the folder name.")
            return

        logger.info(f"Hashing files for {plugin_id}...")
        hashes = {}
        for root, dirs, files in os.walk(plugin_path):
            # Skip ignored directories
            dirs[:] = [d for d in dirs if d not in IGNORE_LIST]
            
            for file in sorted(files):
                if file in IGNORE_LIST:
                    continue
                
                rel_path = os.path.relpath(os.path.join(root, file), plugin_path)
                
                # Check extension (Simplified version of TrustManager logic)
                if any(file.endswith(ext) for ext in MANDATORY_EXTENSIONS):
                    hashes[rel_path] = self._hash_file(Path(root) / file)

        # Update Manifest
        if "integrity" not in manifest:
            manifest["integrity"] = {}
        manifest["integrity"]["hashes"] = hashes
        
        with open(manifest_file, "w") as f:
            json.dump(manifest, f, indent=4)

        # Sign Manifest (Canonicalized)
        manifest_bytes = json.dumps(manifest, sort_keys=True).encode()
        signature = private_key.sign(manifest_bytes)

        # Write signature.bin
        with open(plugin_path / "signature.bin", "wb") as f:
            f.write(signature)

        # Write trust_chain.json (New Format)
        # 1. Assemble the chain starting with this developer
        pub_bytes = public_key.public_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PublicFormat.Raw
        )
        
        # Bottom link: Developer (Leaf of the chain)
        dev_link = TrustLink(
            subject_name=manifest.get("author", "Unknown Developer"),
            subject_pub=pub_bytes.hex(),
            issuer_name="Unknown", # Will be filled if delegation exists
            signature="0" * 128    # Placeholder for developer link
        )
        
        links = [dev_link]
        
        # 2. Add Parent Delegations if they exist
        if self.delegation_path.exists():
            try:
                parent_chain = TrustChain.from_file(self.delegation_path)
                if parent_chain:
                    # Update developer link's issuer to match the first link in parent chain's subject
                    dev_link.issuer_name = parent_chain.links[0].subject_name
                    # The delegation Alice has from Bob is: Subject=Alice, Issuer=Bob, Sig=Bob(Alice).
                    # Alice's chain should be: [AliceLink, BobLink, ..., RootLink]
                    links = parent_chain.links
            except Exception as e:
                logger.warning(f"Failed to load delegation chain: {e}")

        chain = TrustChain(links=links)
        with open(plugin_path / "trust_chain.json", "w") as f:
            f.write(chain.to_json())

        logger.info(f"Successfully signed {plugin_id}")
        logger.info(f"Generated: signature.bin, trust_chain.json")

    def delegate_identity(self, subject_pub_file: Path, subject_name: str, authority_key_path: Optional[Path] = None):
        """Signs another developer's public key using an Authority key.
        
        If authority_key_path is None, it uses the local developer key (Lab trusting Researcher).
        If authority_key_path is provided, it uses that (e.g. BioPro Core Root).
        """
        if authority_key_path:
            with open(authority_key_path, "rb") as f:
                private_key = serialization.load_pem_private_key(f.read(), password=None)
            with open(authority_key_path.with_suffix(".pub") if authority_key_path.with_suffix(".pub").exists() else self.public_key_path, "rb") as f:
                # We need the authority's name/ID
                auth_name = "BioPro Core Authority" if "root" in str(authority_key_path).lower() else "Authority"
        else:
            private_key = self.load_private_key()
            auth_name = "Me"

        if not subject_pub_file.exists():
            logger.error(f"Subject public key file not found: {subject_pub_file}")
            return

        with open(subject_pub_file, "rb") as f:
            sub_pub_bytes = f.read()
            if len(sub_pub_bytes) != 32:
                try:
                    pub = serialization.load_pem_public_key(sub_pub_bytes)
                    sub_pub_bytes = pub.public_bytes(encoding=serialization.Encoding.Raw, format=serialization.PublicFormat.Raw)
                except Exception:
                    logger.error("Invalid public key format.")
                    return

        signature = private_key.sign(sub_pub_bytes)
        
        # Create a TrustLink for the subject (e.g. Researcher signed by Lab)
        new_link = TrustLink(
            subject_name=subject_name,
            subject_pub=sub_pub_bytes.hex(),
            issuer_name=auth_name,
            signature=signature.hex()
        )
        
        links = [new_link]
        
        # If I have my own delegation (e.g. I am a Lab and Uni trusts me), I must include it
        if not authority_key_path and self.delegation_path.exists():
            parent_chain = TrustChain.from_file(self.delegation_path)
            if parent_chain:
                new_link.issuer_name = parent_chain.links[0].subject_name
                links.extend(parent_chain.links)

        chain = TrustChain(links=links)
        output_file = Path(f"delegation_{subject_name.lower().replace(' ', '_')}.json")
        with open(output_file, "w") as f:
            f.write(chain.to_json())
            
        logger.info(f"Delegation file created: {output_file}")
        logger.info(f"Move this to the developer's keys folder as delegation.json")

    def _hash_file(self, path: Path) -> str:
        hasher = hashlib.sha256()
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(4096), b""):
                hasher.update(chunk)
        return hasher.hexdigest()

    def print_registry_entry(self):
        """Prints the JSON block for the registry."""
        if not self.public_key_path.exists():
            logger.error("No identity found. Run 'init' first.")
            return

        with open(self.public_key_path, "rb") as f:
            pub_hex = f.read().hex()

        entry = {
            "developer_id": "Your-GitHub-Username",
            "public_key": pub_hex
        }
        print("\n--- COPY THIS TO YOUR registry.json ---")
        print(json.dumps(entry, indent=4))
        print("---------------------------------------")

def main():
    import argparse
    parser = argparse.ArgumentParser(description="BioPro Plugin Signer")
    subparsers = parser.add_subparsers(dest="command")

    subparsers.add_parser("init")
    
    sign_parser = subparsers.add_parser("sign")
    sign_parser.add_argument("path", help="Path to plugin folder")

    delegate_parser = subparsers.add_parser("delegate")
    delegate_parser.add_argument("pub_path", help="Path to researcher's public.pub")
    delegate_parser.add_argument("name", help="Researcher's name")
    delegate_parser.add_argument("--authority", help="Path to authority private key (optional)")

    subparsers.add_parser("registry")

    args = parser.parse_args()
    signer = PluginSigner()

    if args.command == "init":
        signer.init_identity()
    elif args.command == "sign":
        signer.sign_plugin(Path(args.path))
    elif args.command == "delegate":
        signer.delegate_identity(Path(args.pub_path), args.name, Path(args.authority) if args.authority else None)
    elif args.command == "registry":
        signer.print_registry_entry()
    else:
        parser.print_help()

if __name__ == "__main__":
    main()
