import pandas as pd
p = r"c:\Users\Admin\myquant\data\depth\ES_depth_2026-07-17.csv"
# header: Time,Ev,Side,Pos,Price,Size
df = pd.read_csv(p)
print("rows:", len(df), "| cols:", list(df.columns))
print("time span:", df.Time.iloc[0], "->", df.Time.iloc[-1])
t = pd.to_datetime(df.Time)
print("duration:", (t.iloc[-1] - t.iloc[0]))
print("\nEvent breakdown (Ev):")
print(df.Ev.value_counts().to_dict())
print("\nSide breakdown:", df.Side.value_counts().to_dict())
print("book levels (Pos) seen:", sorted(df[df.Ev != 'T'].Pos.unique().tolist()))
print("price range:", df.Price.min(), "-", df.Price.max())
tr = df[df.Ev == 'T']
print("\ntrades (T rows):", len(tr), "| total traded vol:", int(tr.Size.sum()),
      "| buy(A)/sell(B):", tr[tr.Side == 'A'].Size.sum(), "/", tr[tr.Side == 'B'].Size.sum())
book = df[df.Ev != 'T']
print("book updates:", len(book), "| add/update/remove:", book.Ev.value_counts().to_dict())
print("\nfirst 6 rows:")
print(df.head(6).to_string(index=False))
print("\nlast 4 rows:")
print(df.tail(4).to_string(index=False))
# rough rows/min to gauge firehose
mins = max((t.iloc[-1] - t.iloc[0]).total_seconds() / 60, 1)
print(f"\n~{len(df)/mins:,.0f} rows/min  ({len(df)/mins/60:,.0f}/sec)")
