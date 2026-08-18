from AlgorithmImports import *

class NorthstarConfluence(QCAlgorithm):
    """Independent LEAN implementation of the Northstar daily confluence rules."""
    def initialize(self):
        self.set_start_date(2016,1,1);self.set_end_date(2026,8,1);self.set_cash(100000)
        ticker=self.get_parameter("symbol") or "SPY";self.symbol=self.add_equity(ticker,Resolution.DAILY).symbol
        self.ema50=self.ema(self.symbol,50,Resolution.DAILY);self.ema200=self.ema(self.symbol,200,Resolution.DAILY)
        self.rsi=self.rsi(self.symbol,14,MovingAverageType.WILDERS,Resolution.DAILY);self.macd=self.macd(self.symbol,12,26,9,MovingAverageType.EXPONENTIAL,Resolution.DAILY);self.atr=self.atr(self.symbol,14,MovingAverageType.WILDERS,Resolution.DAILY)
        self.set_warm_up(220,Resolution.DAILY);self.entry_bar=None;self.entry_price=None;self.stop_price=None;self.target_price=None;self.max_r=0
    def on_data(self,data):
        if self.is_warming_up or not data.contains_key(self.symbol):return
        bar=data[self.symbol];invested=self.portfolio[self.symbol].invested
        if invested:
            risk=self.entry_price-self.stop_price;self.max_r=max(self.max_r,(bar.high-self.entry_price)/risk);held=(self.time.date()-self.entry_bar).days
            if (held>=10 and self.max_r<.5) or held>=28:self.liquidate(self.symbol,"Northstar time exit")
            return
        higher=bar.close>self.ema200.current.value and bar.close>self.ema50.current.value
        confirmations=int(self.macd.current.value>self.macd.signal.current.value)+int(self.rsi.current.value>50)
        near_demand=abs(bar.close-self.ema50.current.value)<=self.atr.current.value*1.25
        if not (higher and near_demand and confirmations>=2):return
        stop=min(bar.low-self.atr.current.value*.15,self.ema50.current.value-self.atr.current.value*.65);risk=bar.close-stop
        if risk<=0 or risk/bar.close>.12:return
        quantity=min(int(self.portfolio.total_portfolio_value*.0075/risk),int(self.portfolio.total_portfolio_value*.20/bar.close))
        if quantity<=0:return
        ticket=self.market_order(self.symbol,quantity);self.entry_price=bar.close;self.stop_price=stop;self.target_price=bar.close+2*risk;self.entry_bar=self.time.date();self.max_r=0
        self.stop_market_order(self.symbol,-quantity,stop,"Structure stop");self.limit_order(self.symbol,-quantity,self.target_price,"2R target")
