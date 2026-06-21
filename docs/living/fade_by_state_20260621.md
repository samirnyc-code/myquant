# Fade by state (2026-06-21)

ER>=0.30 pinned 1.0R. 4439 filled. 'orig' = as-traded; 'fade' = mirror trade.

## Q1 — fade the whole bucket? (orig exp vs fading every signal in it)

Only worth fading if orig exp is clearly negative AND fade exp clearly positive.

| bucket | orig n | orig exp | orig PF | fade n | fade exp | fade win% |
|---|---|---|---|---|---|---|
| ALL | 4439 | $87 | 1.28 | 4439 | $-124 | 42% |
| disc=disc_aligned | 2138 | $73 | 1.24 | 2138 | $-117 | 42% |
| disc=disc_counter | 1462 | $92 | 1.30 | 1462 | $-124 | 42% |
| disc=rotation | 708 | $149 | 1.43 | 708 | $-179 | 39% |
| disc=na | 131 | $-72 | 0.80 | 131 | $43 | 51% |
| eth=eth_break | 1904 | $109 | 1.35 | 1904 | $-152 | 41% |
| eth=eth_inside | 1887 | $81 | 1.25 | 1887 | $-115 | 42% |
| eth=eth_counter | 517 | $68 | 1.28 | 517 | $-99 | 41% |
| eth=na | 131 | $-72 | 0.80 | 131 | $43 | 51% |
| adr_bkt=0.5-1.0 | 2129 | $73 | 1.22 | 2129 | $-110 | 42% |
| adr_bkt=<0.5 | 1006 | $110 | 1.39 | 1006 | $-151 | 40% |
| adr_bkt=1.0-1.5 | 835 | $43 | 1.14 | 835 | $-82 | 43% |
| adr_bkt=>1.5 | 320 | $279 | 1.94 | 320 | $-319 | 41% |
| adr_bkt=na | 147 | $-42 | 0.87 | 147 | $12 | 48% |
| open_loc=inside | 2585 | $113 | 1.37 | 2585 | $-149 | 41% |
| open_loc=above | 917 | $68 | 1.25 | 917 | $-106 | 40% |
| open_loc=below | 806 | $50 | 1.13 | 806 | $-93 | 44% |
| open_loc=na | 131 | $-72 | 0.80 | 131 | $43 | 51% |
| balance_lbl=non-balance | 3731 | $75 | 1.25 | 3731 | $-114 | 42% |
| balance_lbl=balance | 708 | $149 | 1.43 | 708 | $-179 | 39% |

## Q2 — of the LOSING trades, do they reverse? (faded losers by state)

All losers: 2004 trades, orig $-1,386,587; faded fills 2004, net $1,265,300 (exp $631, win 93%).

| bucket | n losers | orig loss | faded net | fade exp | fade win% |
|---|---|---|---|---|---|
| disc=disc_aligned | 974 | $-642,609 | $574,016 | $589 | 92% |
| disc=disc_counter | 662 | $-453,536 | $421,489 | $637 | 94% |
| disc=rotation | 298 | $-243,762 | $225,476 | $757 | 93% |
| disc=na | 70 | $-46,680 | $44,320 | $633 | 96% |
| eth=eth_inside | 856 | $-616,607 | $571,218 | $667 | 93% |
| eth=eth_break | 849 | $-599,764 | $537,548 | $633 | 92% |
| eth=eth_counter | 229 | $-123,536 | $112,214 | $490 | 92% |
| eth=na | 70 | $-46,680 | $44,320 | $633 | 96% |
| adr_bkt=0.5-1.0 | 962 | $-690,244 | $634,806 | $660 | 93% |
| adr_bkt=<0.5 | 434 | $-286,880 | $254,645 | $587 | 93% |
| adr_bkt=1.0-1.5 | 392 | $-265,984 | $243,803 | $622 | 91% |
| adr_bkt=>1.5 | 141 | $-95,427 | $86,923 | $616 | 94% |
| adr_bkt=na | 75 | $-48,052 | $45,123 | $602 | 95% |
| open_loc=inside | 1150 | $-789,926 | $722,111 | $628 | 93% |
| open_loc=above | 401 | $-245,286 | $219,827 | $548 | 92% |
| open_loc=below | 383 | $-304,695 | $279,043 | $729 | 93% |
| open_loc=na | 70 | $-46,680 | $44,320 | $633 | 96% |
| balance_lbl=non-balance | 1706 | $-1,142,826 | $1,039,824 | $610 | 92% |
| balance_lbl=balance | 298 | $-243,762 | $225,476 | $757 | 93% |
