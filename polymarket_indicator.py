import requests
import json
import csv
import time
from datetime import datetime

class PolymarketSniperV6_1:
    def __init__(self):
        self.CLOB_URL = "https://clob.polymarket.com"
        self.GAMMA_URL = "https://gamma-api.polymarket.com/events"
        self.CSV_FILENAME = "polymarket_analysis.csv"
        self.session = requests.Session()
        
        # --- factors ---
        self.MIN_24H_VOL = 100000   
        self.MIN_LIQUIDITY = 50000  
        self.MIN_EXEC_LIQUIDITY = 1000  # each option at 'Best Ask' needs at least $1000 liquidity
        self.ARB_NET_THRESHOLD = 0.990  # 1% profit after costs
        self.MAX_OUTCOMES_SCAN = 10     # only scan first 10 outcomes for multi-option markets
        
    def get_price_and_depth(self, token_id):
        """automatically fetch best sell price and depth from CLOB orderbook"""
        try:
            # fetch Orderbook data
            url = f"{self.CLOB_URL}/book"
            res = self.session.get(url, params={'token_id': token_id}, timeout=2)
            if res.status_code == 200:
                data = res.json()
                asks = data.get('asks', [])
                if asks:
                    best_ask = float(asks[0]['price'])
                    size = float(asks[0]['size'])
                    return best_ask, best_ask * size # return price and total value (USDC)
        except: pass
        return 0.99, 0

    def run_scan(self):
        start_time = datetime.now()
        print(f"[{start_time.strftime('%H:%M:%S')}] launching: locating arbitrage opportunities...")
        
        headers = ["status", "net_arb_pct", "real_cost_sum", "min_ask_liq", "type", "num_outcomes", "vol_24h", "age_sec", "title", "url"]
        with open(self.CSV_FILENAME, 'w', newline='', encoding='utf-8-sig') as f:
            csv.DictWriter(f, fieldnames=headers).writeheader()

        try:
            # 1. fetch top events by 24H volume
            top_events = self.session.get(self.GAMMA_URL, params={'closed': 'false', 'limit': 60, 'order': 'volume24hr', 'ascending': 'false'}).json()
            
            for e in top_events:
                title = e.get('title', 'Unknown')
                vol_24hr = float(e.get('volume24hr', 0) or 0)
                liq = float(e.get('liquidity', 0) or 0)

                # basic filters
                if vol_24hr < self.MIN_24H_VOL or liq < self.MIN_LIQUIDITY: continue
                if any(k in title.upper() for k in ["NFL", "NBA", "MLB", "SOCCER", "BOX OFFICE"]): continue

                markets = e.get('markets', [])
                num_outcomes = len(markets)
                is_binary = (num_outcomes == 1)
                is_full = True if (is_binary or num_outcomes <= self.MAX_OUTCOMES_SCAN) else False
                
                real_cost_sum = 0
                min_depth = float('inf')
                
                print(f"  > snipper scan: {title[:45]}...")

                # 2. determine real cost sum and min depth
                for m in markets[:self.MAX_OUTCOMES_SCAN]:
                    token_ids = json.loads(m.get('clobTokenIds', '[]'))
                    if is_binary and len(token_ids) >= 2:
                        # Binary check
                        p_y, d_y = self.get_price_and_depth(token_ids[0])
                        p_n, d_n = self.get_price_and_depth(token_ids[1])
                        real_cost_sum = p_y + p_n
                        min_depth = min(d_y, d_n)
                    else:
                        # Multi check (Yes Only)
                        p, d = self.get_price_and_depth(token_ids[0]) if token_ids else (0.99, 0)
                        real_cost_sum += p
                        min_depth = min(min_depth, d)

                # 3. arbitrage calculation
                arb_pct = max(0, 1 - real_cost_sum)
                age_sec = int((datetime.now() - start_time).total_seconds())
                
                # determine status
                if is_binary and arb_pct > (1 - self.ARB_NET_THRESHOLD) and min_depth >= self.MIN_EXEC_LIQUIDITY:
                    status = "TRUE_BINARY_ARB"
                elif is_full and arb_pct > (1 - self.ARB_NET_THRESHOLD) and num_outcomes <= 6:
                    status = "HIGH_CONFIDENCE_ARB" if min_depth >= self.MIN_EXEC_LIQUIDITY else "THEORETICAL_ARB"
                elif is_full and arb_pct > 0.005:
                    status = "YES_ARBITRAGE"
                elif not is_full and arb_pct > 0.05:
                    status = "IGNORE_INCOMPLETE"
                else:
                    status = "NO"

                # 4. reacord result
                res_row = {
                    "status": status,
                    "net_arb_pct": f"{arb_pct*100:.2f}%",
                    "real_cost_sum": f"{real_cost_sum:.4f}",
                    "min_ask_liq": f"${min_depth:,.0f}",
                    "type": "BINARY" if is_binary else "MULTI",
                    "num_outcomes": num_outcomes,
                    "vol_24h": f"${vol_24hr:,.0f}",
                    "age_sec": age_sec,
                    "title": title,
                    "url": f"https://polymarket.com/event/{e.get('slug', '')}"
                }
                
                with open(self.CSV_FILENAME, 'a', newline='', encoding='utf-8-sig') as f:
                    csv.DictWriter(f, fieldnames=headers).writerows([res_row])
                
                time.sleep(0.1)

            print(f"\n task done, file name: {self.CSV_FILENAME}")

        except Exception as err:
            print(f"error status: {err}")

if __name__ == "__main__":
    scanner = PolymarketSniperV6_1()
    scanner.run_scan()