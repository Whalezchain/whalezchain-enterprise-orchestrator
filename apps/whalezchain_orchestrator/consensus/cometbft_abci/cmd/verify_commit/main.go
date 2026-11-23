// Offline-capable verification of CometBFT signed commits against pinned
// genesis validator powers and canonical WhalezChain application hashes.
// This tool is read-only and cannot sign, mint, settle, or run a chain.
package main

import (
	"bytes"
	"context"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"errors"
	"flag"
	"fmt"
	"io"
	"net/url"
	"os"
	"strings"
	"time"

	cmtjson "github.com/cometbft/cometbft/libs/json"
	client "github.com/cometbft/cometbft/rpc/client/http"
	"github.com/cometbft/cometbft/types"
)

const proofSchema = "whalezchain.cometbft.signed_header.v1"
const maxProofBytes = 1 << 20

type signedProof struct {
	Schema          string          `json:"schema"`
	ChainID         string          `json:"chain_id"`
	Height          int64           `json:"height"`
	SignedHeader    json.RawMessage `json:"signed_header"`
	CanonicalCommit bool            `json:"canonical_commit"`
}

// A state commitment at CometBFT header H authenticates the application
// state after H-1. WhalezChain block heights begin at 0, so the certified
// WhalezChain block is H-2. Never promote the *current* H block from this.
func verifyHeader(genesisPath string, h types.SignedHeader, height int64, expectedAppHash string) (map[string]any, error) {
	expected, err := hex.DecodeString(expectedAppHash)
	if err != nil || len(expected) != 32 {
		return nil, fmt.Errorf("expected application hash must be 32 bytes")
	}
	if height < 2 {
		return nil, fmt.Errorf("height must be >=2")
	}
	genesis, err := types.GenesisDocFromFile(genesisPath)
	if err != nil {
		return nil, err
	}
	if len(genesis.Validators) != 4 {
		return nil, fmt.Errorf("trusted v1 genesis must contain exactly four validators")
	}
	vals := make([]*types.Validator, 0, len(genesis.Validators))
	for _, v := range genesis.Validators {
		if v.PubKey == nil || v.Power <= 0 {
			return nil, fmt.Errorf("invalid pinned validator")
		}
		vals = append(vals, types.NewValidator(v.PubKey, v.Power))
	}
	validators := types.NewValidatorSet(vals)
	if err := h.ValidateBasic(genesis.ChainID); err != nil {
		return nil, err
	}
	if h.Height != height {
		return nil, fmt.Errorf("signed header height mismatch")
	}
	if !bytes.Equal(h.Header.ValidatorsHash, validators.Hash()) {
		return nil, fmt.Errorf("signed validator set differs from trusted genesis")
	}
	if !bytes.Equal(h.Header.AppHash, expected) {
		return nil, fmt.Errorf("signed application hash differs from canonical WhalezChain state")
	}
	if err := validators.VerifyCommitLightAllSignatures(
		genesis.ChainID, h.Commit.BlockID, height, h.Commit,
	); err != nil {
		return nil, fmt.Errorf("cryptographic quorum proof rejected: %w", err)
	}
	count := 0
	for _, s := range h.Commit.Signatures {
		if s.BlockIDFlag == types.BlockIDFlagCommit {
			count++
		}
	}
	if count < 3 {
		return nil, fmt.Errorf("insufficient validator votes for committed block")
	}
	return map[string]any{
		"verified":                      true,
		"network_chain_id":              genesis.ChainID,
		"height":                        height,
		"certified_whalez_block_height": height - 2,
		"validator_count":               len(vals),
		"signed_votes_for_block":        count,
		"commit_block_hash":             hex.EncodeToString(h.Commit.BlockID.Hash),
		"trusted_validators_hash":       hex.EncodeToString(validators.Hash()),
		"signed_header_prior_app_hash":  hex.EncodeToString(h.Header.AppHash),
		"checked_against_canonical_WhalezChain_app_hash": true,
	}, nil
}

func fetchRPC(rpcURL string, height int64) (types.SignedHeader, error) {
	u, err := url.Parse(rpcURL)
	if err != nil {
		return types.SignedHeader{}, err
	}
	if u.Scheme != "http" || !strings.HasPrefix(u.Host, "127.0.0.1:") || u.RawQuery != "" {
		return types.SignedHeader{}, fmt.Errorf("only private loopback RPC is allowed")
	}
	rpc, err := client.New(rpcURL, "/websocket")
	if err != nil {
		return types.SignedHeader{}, err
	}
	ctx, cancel := context.WithTimeout(context.Background(), 8*time.Second)
	defer cancel()
	response, err := rpc.Commit(ctx, &height)
	if err != nil {
		return types.SignedHeader{}, err
	}
	if !response.CanonicalCommit {
		return types.SignedHeader{}, fmt.Errorf("RPC commit is not canonical")
	}
	return response.SignedHeader, nil
}

func exportProof(path string, header types.SignedHeader) error {
	if path == "" {
		return nil
	}
	bytesHeader, err := cmtjson.Marshal(header)
	if err != nil {
		return err
	}
	doc := signedProof{
		Schema:          proofSchema,
		ChainID:         header.ChainID,
		Height:          header.Height,
		SignedHeader:    bytesHeader,
		CanonicalCommit: true,
	}
	content, err := json.MarshalIndent(doc, "", "  ")
	if err != nil {
		return err
	}
	if len(content) > maxProofBytes {
		return errors.New("proof exceeds bounded size")
	}
	// O_EXCL refuses existing files and symlinks; no overwrite of evidence.
	f, err := os.OpenFile(path, os.O_WRONLY|os.O_CREATE|os.O_EXCL, 0600)
	if err != nil {
		return err
	}
	defer f.Close()
	if _, err := f.Write(append(content, '\n')); err != nil {
		f.Close()
		os.Remove(path)
		return err
	}
	if err := f.Sync(); err != nil {
		f.Close()
		os.Remove(path)
		return err
	}
	return nil
}

func readProof(path string, expectedHeight int64) (types.SignedHeader, string, error) {
	preOpen, err := os.Lstat(path)
	if err != nil {
		return types.SignedHeader{}, "", err
	}
	if !preOpen.Mode().IsRegular() {
		return types.SignedHeader{}, "", fmt.Errorf("proof cannot be a symlink or special file")
	}
	file, err := os.Open(path)
	if err != nil {
		return types.SignedHeader{}, "", err
	}
	defer file.Close()
	info, err := file.Stat()
	if err != nil {
		return types.SignedHeader{}, "", err
	}
	if !info.Mode().IsRegular() || !os.SameFile(preOpen, info) || info.Size() > maxProofBytes || info.Size() == 0 {
		return types.SignedHeader{}, "", fmt.Errorf("invalid proof file size/type")
	}
	contents := make([]byte, info.Size())
	if _, err := io.ReadFull(file, contents); err != nil {
		return types.SignedHeader{}, "", err
	}
	var proof signedProof
	decoder := json.NewDecoder(bytes.NewReader(contents))
	decoder.DisallowUnknownFields()
	if err := decoder.Decode(&proof); err != nil {
		return types.SignedHeader{}, "", err
	}
	var trailing any
	if err := decoder.Decode(&trailing); err != io.EOF {
		return types.SignedHeader{}, "", fmt.Errorf("unexpected trailing proof content")
	}
	if proof.Schema != proofSchema || !proof.CanonicalCommit || proof.Height != expectedHeight {
		return types.SignedHeader{}, "", fmt.Errorf("proof identity/schema/height mismatch")
	}
	var header types.SignedHeader
	if err := cmtjson.Unmarshal(proof.SignedHeader, &header); err != nil {
		return types.SignedHeader{}, "", fmt.Errorf("cannot decode signed header: %w", err)
	}
	if header.Height != proof.Height || header.ChainID != proof.ChainID {
		return types.SignedHeader{}, "", fmt.Errorf("proof envelope and signed header differ")
	}
	digest := sha256.Sum256(contents)
	return header, hex.EncodeToString(digest[:]), nil
}

func main() {
	rpc := flag.String("rpc", "", "private CometBFT loopback RPC (online mode only)")
	genesis := flag.String("genesis", "", "separately trusted genesis JSON")
	height := flag.Int64("height", 0, "signed header height, not state height")
	appHash := flag.String("expected-apphash", "", "application hash independently computed from WhalezChain state")
	proofOut := flag.String("proof-out", "", "create private bounded signed-header proof, refuse overwriting")
	proofIn := flag.String("proof-in", "", "verify previously exported proof without any network")
	flag.Parse()
	if *genesis == "" || *height < 2 || *appHash == "" {
		fmt.Fprintln(os.Stderr, "VERIFICATION_FAILED: genesis, height and expected-apphash are required")
		os.Exit(2)
	}
	if (*proofIn != "" && (*rpc != "" || *proofOut != "")) || (*proofIn == "" && *rpc == "") {
		fmt.Fprintln(os.Stderr, "VERIFICATION_FAILED: choose online RPC or offline proof input")
		os.Exit(2)
	}
	var header types.SignedHeader
	var proofHash string
	var err error
	if *proofIn != "" {
		header, proofHash, err = readProof(*proofIn, *height)
	} else {
		header, err = fetchRPC(*rpc, *height)
	}
	if err == nil {
		var result map[string]any
		result, err = verifyHeader(*genesis, header, *height, *appHash)
		if err == nil {
			if *proofOut != "" {
				err = exportProof(*proofOut, header)
			}
			if err == nil {
				result["verification_mode"] = "live_rpc_cryptographic"
				if *proofIn != "" {
					result["verification_mode"] = "offline_signature_cryptographic"
					result["proof_sha256"] = proofHash
				}
				encoded, encodeErr := json.Marshal(result)
				if encodeErr != nil {
					err = encodeErr
				} else {
					fmt.Println(string(encoded))
					return
				}
			}
		}
	}
	fmt.Fprintln(os.Stderr, "VERIFICATION_FAILED:", err)
	os.Exit(2)
}
