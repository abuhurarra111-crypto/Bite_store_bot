# 🆕 v146 — BEP20/Binance on-chain amount-tolerance fix + address-paste guard
# + ProdSeller pseudo-stock.
#
# Root cause (verified live 2026-08-06/07):
#   `_usdt_amount_match` used a hard 0.0001 tolerance. Real on-chain USDT
#   deposits routinely arrive slightly ABOVE the order amount (fee buffer),
#   e.g. order 1.0 USDT received 1.0008888. Every such payment failed
#   auto-verification and the orders were auto-cancelled after 60 min.
#
# Fix:
#   - anchored (user pasted TXID / Bybit sender UID): tol = max(0.05, 1%)
#   - amount-only (auto-verify, no txid):           tol = max(0.02, 0.5%)
import os
import sys
import pytest

os.environ.setdefault("DB_PATH", "/tmp/test_v146.db")

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import handlers_order as ho


class TestUsdtAmountMatch:
    def test_old_broken_cases_now_match_anchored(self):
        """Real deposits from Binance history 2026-08-06 must match their orders."""
        assert ho._usdt_amount_match(1.0008888, 1.0, anchored=True)
        assert ho._usdt_amount_match(3.00268234, 3.0, anchored=True)
        assert ho._usdt_amount_match(2.00192625, 2.0, anchored=True)
        assert ho._usdt_amount_match(1.00099815, 1.0, anchored=True)

    def test_amount_only_still_matches_buffer(self):
        """Auto-verify (no pasted txid) still accepts small fee buffers."""
        assert ho._usdt_amount_match(1.0008888, 1.0, anchored=False)
        assert ho._usdt_amount_match(2.00192625, 2.0, anchored=False)

    def test_exact_amounts_still_match(self):
        assert ho._usdt_amount_match(25.0, 25.0, anchored=True)
        assert ho._usdt_amount_match(25.0, 25.0, anchored=False)
        assert ho._usdt_amount_match(0.89, 0.89, anchored=True)

    def test_materially_different_rejected(self):
        """A 50%-over deposit must NEVER match."""
        assert not ho._usdt_amount_match(1.50, 1.0, anchored=False)
        assert not ho._usdt_amount_match(1.50, 1.0, anchored=True)
        assert not ho._usdt_amount_match(0.5, 1.0, anchored=False)
        assert not ho._usdt_amount_match(2.0, 1.0, anchored=False)

    def test_explicit_tolerance_still_honored(self):
        assert ho._usdt_amount_match(1.0001, 1.0, tolerance=0.0001)
        assert not ho._usdt_amount_match(1.001, 1.0, tolerance=0.0001)


class TestAddressPasteGuard:
    def test_bep20_address_detected(self):
        cfg = {"address": "0xe171a20f64b002b839344f67b04620c8a90d1f78"}
        assert ho._looks_like_deposit_address("0xe171a20f64b002b839344f67b04620c8a90d1f78", cfg)
        # address pasted with extra junk text (real observed case)
        assert ho._looks_like_deposit_address(
            "0xe171a20f64b002b839344f67b04620c8a90d1f78\n\nSend amount this adrress usdt bep20 ok", cfg)

    def test_tron_address_detected(self):
        assert ho._looks_like_deposit_address(
            "TAYv4LPE92rixGsr2sKe3Pz8mGfFU5cDW7",
            {"address": "TAYv4LPE92rixGsr2sKe3Pz8mGfFU5cDW7"})

    def test_txid_not_mistaken_for_address(self):
        # BEP20 txid = 0x + 64 hex; address = 0x + 40 hex
        txid = "0x" + "a" * 64
        assert not ho._looks_like_deposit_address(txid, {"address": "0x" + "b" * 40})
        # short garbage
        assert not ho._looks_like_deposit_address("abc123", None)
