// Independently check CometBFT's signed commit against a pinned genesis
// validator set and the prior WhalezChain canonical application hash.
// No private keys, RPC writes, or production activation.
package main

import (
	"bytes"
	"context"
	"encoding/hex"
	"encoding/json"
	"flag"
	"fmt"
	"net/url"
	"os"
	"strings"
	"time"

	client "github.com/cometbft/cometbft/rpc/client/http"
	"github.com/cometbft/cometbft/types"
)

func verify(rpcURL, genesisPath string, height int64, expectedAppHash string) (map[string]any, error) {
	u, err := url.Parse(rpcURL)
	if err != nil {
		return nil, err
	}
	if u.Scheme != "http" || !strings.HasPrefix(u.Host, "127.0.0.1:") {
		return nil, fmt.Errorf("only loopback CometBFT RPC is allowed")
	}
	expected, err := hex.DecodeString(expectedAppHash)
	if err != nil || len(expected) != 32 {
		return nil, fmt.Errorf("expected apphash must be 32 bytes")
	}
	if height < 2 {
		return nil, fmt.Errorf("height must be >=2 for prior application hash")
	}
	genesis, err := types.GenesisDocFromFile(genesisPath)
	if err != nil {
		return nil, err
	}
	if len(genesis.Validators) < 4 {
		return nil, fmt.Errorf("trusted genesis requires four validators")
	}
	vlist := make([]*types.Validator, 0, len(genesis.Validators))
	for _, v := range genesis.Validators {
		if v.PubKey == nil || v.Power <= 0 {
			return nil, fmt.Errorf("invalid trusted validator genesis entry")
		}
		vlist = append(vlist, types.NewValidator(v.PubKey, v.Power))
	}
	validators := types.NewValidatorSet(vlist)
	rpc, err := client.New(rpcURL, "/websocket")
	if err != nil {
		return nil, err
	}
	ctx, cancel := context.WithTimeout(context.Background(), 8*time.Second)
	defer cancel()
	signed, err := rpc.Commit(ctx, &height)
	if err != nil {
		return nil, err
	}
	if !signed.CanonicalCommit {
		return nil, fmt.Errorf("commit is not canonical")
	}
	header := signed.SignedHeader
	if err := header.ValidateBasic(genesis.ChainID); err != nil {
		return nil, err
	}
	if header.Height != height {
		return nil, fmt.Errorf("unexpected header height")
	}
	if !bytes.Equal(header.Header.ValidatorsHash, validators.Hash()) {
		return nil, fmt.Errorf("live validator set differs from pinned genesis")
	}
	if !bytes.Equal(header.Header.AppHash, expected) {
		return nil, fmt.Errorf("WhalezChain expected application hash differs from signed header")
	}
	if err := validators.VerifyCommitLightAllSignatures(
		genesis.ChainID, header.Commit.BlockID, height, header.Commit,
	); err != nil {
		return nil, fmt.Errorf("cryptographic commit verification failed: %w", err)
	}
	count := 0
	for _, sig := range header.Commit.Signatures {
		if sig.BlockIDFlag == types.BlockIDFlagCommit {
			count++
		}
	}
	if count < 3 {
		return nil, fmt.Errorf("insufficient actual commit votes")
	}
	return map[string]any{
		"verified":                     true,
		"network_chain_id":             genesis.ChainID,
		"height":                       height,
		"validator_count":              len(validators.Validators),
		"signed_votes_for_block":       count,
		"commit_block_hash":            hex.EncodeToString(header.Commit.BlockID.Hash),
		"trusted_validators_hash":      hex.EncodeToString(validators.Hash()),
		"signed_header_prior_app_hash": hex.EncodeToString(header.Header.AppHash),
		"checked_against_canonical_WhalezChain_app_hash": true,
	}, nil
}

func main() {
	rpc := flag.String("rpc", "", "private CometBFT loopback RPC")
	genesis := flag.String("genesis", "", "trusted CometBFT genesis JSON")
	height := flag.Int64("height", 0, "known finalized height")
	appHash := flag.String("expected-apphash", "", "previous WhalezChain state application hash")
	flag.Parse()
	result, err := verify(*rpc, *genesis, *height, *appHash)
	if err != nil {
		fmt.Fprintln(os.Stderr, "VERIFICATION_FAILED:", err)
		os.Exit(2)
	}
	encoded, err := json.Marshal(result)
	if err != nil {
		fmt.Fprintln(os.Stderr, err)
		os.Exit(3)
	}
	fmt.Println(string(encoded))
}
