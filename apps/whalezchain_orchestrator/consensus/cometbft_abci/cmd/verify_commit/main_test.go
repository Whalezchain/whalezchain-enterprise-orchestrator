package main

import (
	"os"
	"path/filepath"
	"strings"
	"testing"

	"github.com/cometbft/cometbft/types"
)

func TestOfflineProofRejectsMissingAndMalformedInputs(t *testing.T) {
	root := t.TempDir()
	if _, _, err := readProof(filepath.Join(root, "missing.json"), 4); err == nil {
		t.Fatal("missing proof must fail closed")
	}

	empty := filepath.Join(root, "empty.json")
	if err := os.WriteFile(empty, nil, 0600); err != nil {
		t.Fatal(err)
	}
	if _, _, err := readProof(empty, 4); err == nil {
		t.Fatal("empty proof accepted")
	}

	invalid := filepath.Join(root, "invalid.json")
	if err := os.WriteFile(invalid, []byte("{invalid"), 0600); err != nil {
		t.Fatal(err)
	}
	if _, _, err := readProof(invalid, 4); err == nil {
		t.Fatal("malformed proof accepted")
	}

	trailing := filepath.Join(root, "trailing.json")
	if err := os.WriteFile(trailing, []byte("{}{}"), 0600); err != nil {
		t.Fatal(err)
	}
	if _, _, err := readProof(trailing, 4); err == nil {
		t.Fatal("trailing proof payload accepted")
	}
}

func TestOfflineProofRejectsSymlinkAndOversizedFile(t *testing.T) {
	root := t.TempDir()
	target := filepath.Join(root, "target.json")
	if err := os.WriteFile(target, []byte("{}"), 0600); err != nil {
		t.Fatal(err)
	}
	link := filepath.Join(root, "link.json")
	if err := os.Symlink(target, link); err != nil {
		t.Fatal(err)
	}
	if _, _, err := readProof(link, 4); err == nil {
		t.Fatal("proof symlink must never be followed")
	}

	oversize := filepath.Join(root, "oversize.json")
	if err := os.WriteFile(oversize, []byte(strings.Repeat("z", maxProofBytes+1)), 0600); err != nil {
		t.Fatal(err)
	}
	if _, _, err := readProof(oversize, 4); err == nil {
		t.Fatal("oversized proof accepted")
	}
}

func TestOfflineProofRejectsMismatchAndUntrustedEnvelope(t *testing.T) {
	root := t.TempDir()
	file := filepath.Join(root, "untrusted.json")
	fake := []byte(`{"schema":"whalezchain.cometbft.signed_header.v1","chain_id":"forged","height":4,"canonical_commit":false,"signed_header":{}}`)
	if err := os.WriteFile(file, fake, 0600); err != nil {
		t.Fatal(err)
	}
	if _, _, err := readProof(file, 4); err == nil {
		t.Fatal("non-canonical proof was accepted")
	}
	if _, _, err := readProof(file, 5); err == nil {
		t.Fatal("replayed height was accepted")
	}
	if _, err := verifyHeader("does-not-exist", types.SignedHeader{}, 4, "00"); err == nil {
		t.Fatal("invalid expected state commitment accepted")
	}
}
