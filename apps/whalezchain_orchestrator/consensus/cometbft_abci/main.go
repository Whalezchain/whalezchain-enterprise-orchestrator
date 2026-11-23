// ABCI++ front end for the canonical Python WhalezChain state machine.
package main

import (
	"bytes"
	"context"
	"encoding/base64"
	"encoding/hex"
	"encoding/json"
	"errors"
	"flag"
	"fmt"
	"io"
	"log"
	"net"
	"net/http"
	"os"
	"os/signal"
	"syscall"
	"time"

	"github.com/cometbft/cometbft/abci/server"
	abci "github.com/cometbft/cometbft/abci/types"
	"github.com/cometbft/cometbft/version"
)

type app struct {
	abci.BaseApplication
	http *http.Client
}
type answer struct {
	Height          int64    `json:"height"`
	AppHash         string   `json:"app_hash"`
	Accepted        bool     `json:"accepted"`
	Txs             []string `json:"txs"`
	TxCount         int      `json:"tx_count"`
	NetworkChainID  string   `json:"network_chain_id"`
	WhalezBlockHash string   `json:"whalez_block_hash"`
}

func newApp(socket string) *app {
	tr := &http.Transport{DialContext: func(ctx context.Context, _, _ string) (net.Conn, error) {
		return (&net.Dialer{}).DialContext(ctx, "unix", socket)
	}}
	return &app{http: &http.Client{Transport: tr, Timeout: 8 * time.Second}}
}
func (a *app) request(ctx context.Context, method, path string, body any) (answer, error) {
	var raw []byte
	if method == "POST" {
		var err error
		raw, err = json.Marshal(body)
		if err != nil {
			return answer{}, err
		}
	}
	req, err := http.NewRequestWithContext(ctx, method, "http://whalez-private"+path, bytes.NewReader(raw))
	if err != nil {
		return answer{}, err
	}
	if method == "POST" {
		req.Header.Set("Content-Type", "application/json")
	}
	resp, err := a.http.Do(req)
	if err != nil {
		return answer{}, fmt.Errorf("private WhalezChain application unavailable: %w", err)
	}
	defer resp.Body.Close()
	if resp.StatusCode != http.StatusOK {
		return answer{}, fmt.Errorf("WhalezChain rejected %s: HTTP %d", path, resp.StatusCode)
	}
	dec := json.NewDecoder(io.LimitReader(resp.Body, 2000000))
	dec.DisallowUnknownFields()
	var out answer
	err = dec.Decode(&out)
	return out, err
}
func digest(value string) ([]byte, error) {
	if len(value) != 64 {
		return nil, errors.New("invalid WhalezChain app hash")
	}
	return hex.DecodeString(value)
}
func encodeTxs(input [][]byte) []string {
	out := make([]string, len(input))
	for i, tx := range input {
		out[i] = base64.StdEncoding.EncodeToString(tx)
	}
	return out
}
func decodeTxs(input []string) ([][]byte, error) {
	out := make([][]byte, len(input))
	for i, tx := range input {
		b, err := base64.StdEncoding.DecodeString(tx)
		if err != nil {
			return nil, err
		}
		out[i] = b
	}
	return out, nil
}
func (a *app) Info(ctx context.Context, _ *abci.RequestInfo) (*abci.ResponseInfo, error) {
	v, err := a.request(ctx, "GET", "/info", nil)
	if err != nil {
		return nil, err
	}
	b, err := digest(v.AppHash)
	if err != nil {
		return nil, err
	}
	return &abci.ResponseInfo{
		Data: "whalezchain-canonical-application", Version: version.ABCIVersion,
		AppVersion: 1, LastBlockHeight: v.Height, LastBlockAppHash: b,
	}, nil
}
func (a *app) InitChain(ctx context.Context, req *abci.RequestInitChain) (*abci.ResponseInitChain, error) {
	var state struct {
		Hash string `json:"whalez_genesis_hash"`
	}
	if err := json.Unmarshal(req.AppStateBytes, &state); err != nil {
		return nil, err
	}
	if len(state.Hash) != 64 {
		return nil, errors.New("missing genesis hash")
	}
	v, err := a.request(ctx, "POST", "/init", map[string]any{
		"chain_id": req.ChainId, "app_genesis_hash": state.Hash,
	})
	if err != nil {
		return nil, err
	}
	b, err := digest(v.AppHash)
	if err != nil {
		return nil, err
	}
	return &abci.ResponseInitChain{AppHash: b}, nil
}
func (a *app) CheckTx(ctx context.Context, req *abci.RequestCheckTx) (*abci.ResponseCheckTx, error) {
	v, err := a.request(ctx, "POST", "/check", map[string]any{
		"tx": base64.StdEncoding.EncodeToString(req.Tx),
	})
	if err != nil {
		return nil, err
	}
	if !v.Accepted {
		return &abci.ResponseCheckTx{Code: 1, Log: "rejected_by_canonical_state"}, nil
	}
	return &abci.ResponseCheckTx{Code: 0, GasWanted: 1}, nil
}
func (a *app) PrepareProposal(ctx context.Context, req *abci.RequestPrepareProposal) (*abci.ResponsePrepareProposal, error) {
	v, err := a.request(ctx, "POST", "/prepare", map[string]any{
		"txs": encodeTxs(req.Txs), "max_bytes": req.MaxTxBytes,
	})
	if err != nil {
		return nil, err
	}
	txs, err := decodeTxs(v.Txs)
	if err != nil {
		return nil, err
	}
	return &abci.ResponsePrepareProposal{Txs: txs}, nil
}
func (a *app) ProcessProposal(ctx context.Context, req *abci.RequestProcessProposal) (*abci.ResponseProcessProposal, error) {
	v, err := a.request(ctx, "POST", "/process", map[string]any{"txs": encodeTxs(req.Txs)})
	if err != nil {
		return nil, err
	}
	status := abci.ResponseProcessProposal_REJECT
	if v.Accepted {
		status = abci.ResponseProcessProposal_ACCEPT
	}
	return &abci.ResponseProcessProposal{Status: status}, nil
}
func (a *app) FinalizeBlock(ctx context.Context, req *abci.RequestFinalizeBlock) (*abci.ResponseFinalizeBlock, error) {
	v, err := a.request(ctx, "POST", "/finalize", map[string]any{
		"height":           req.Height,
		"block_hash":       hex.EncodeToString(req.Hash),
		"timestamp":        req.Time.UTC().Format(time.RFC3339Nano),
		"proposer_address": hex.EncodeToString(req.ProposerAddress),
		"txs":              encodeTxs(req.Txs),
	})
	if err != nil {
		return nil, err
	}
	if v.TxCount != len(req.Txs) {
		return nil, errors.New("transaction-count mismatch")
	}
	b, err := digest(v.AppHash)
	if err != nil {
		return nil, err
	}
	results := make([]*abci.ExecTxResult, len(req.Txs))
	for i := range results {
		results[i] = &abci.ExecTxResult{Code: 0}
	}
	return &abci.ResponseFinalizeBlock{AppHash: b, TxResults: results}, nil
}
func (a *app) Commit(ctx context.Context, _ *abci.RequestCommit) (*abci.ResponseCommit, error) {
	if _, err := a.request(ctx, "POST", "/commit", map[string]any{}); err != nil {
		return nil, err
	}
	return &abci.ResponseCommit{RetainHeight: 0}, nil
}
func (a *app) Query(_ context.Context, _ *abci.RequestQuery) (*abci.ResponseQuery, error) {
	return &abci.ResponseQuery{Code: 1, Log: "unsafe_queries_disabled"}, nil
}
func main() {
	listen := flag.String("listen", "tcp://127.0.0.1:26658", "private ABCI socket listener")
	socket := flag.String("backend-socket", "", "private WhalezChain UNIX socket")
	flag.Parse()
	if *socket == "" {
		log.Fatal("backend-socket required")
	}
	if len(*listen) < 7 || (*listen)[:6] != "tcp://" {
		log.Fatal("only private TCP listener supported")
	}
	host, _, err := net.SplitHostPort((*listen)[6:])
	if err != nil || host != "127.0.0.1" {
		log.Fatal("ABCI listener must use 127.0.0.1")
	}
	service := server.NewSocketServer(*listen, newApp(*socket))
	if err := service.Start(); err != nil {
		log.Fatal(err)
	}
	log.Print("WhalezChain ABCI++ private listener active")
	ch := make(chan os.Signal, 1)
	signal.Notify(ch, syscall.SIGTERM, syscall.SIGINT)
	<-ch
	if err := service.Stop(); err != nil {
		log.Printf("stop error: %v", err)
	}
}
