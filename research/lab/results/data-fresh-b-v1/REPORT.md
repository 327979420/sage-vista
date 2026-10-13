# data-fresh-b-v1

Engineering check written by the research lab on 2026-10-13; no returns are computed. Every number comes from `result.json` in this folder.

## The question

Freeze shard b of the wider universe (1500 US stocks no rule has seen, from data-fresh-universe-v2) as a dataset with daily history from 1995 and the unadjusted close, and report how much history each year has. (Engineering check: no returns.)

## The short answer

- Built 1500 of 1500 symbols (0.0% missing); earliest bar 1995-01-03. Check passed: **yes**.

## History available at the start of each year

| Year | Trading | ≥50 months | ≥120 months | ≥200 months (monthly EMA200) |
|---|---|---|---|---|
| 2005 | 732 | 525 | 161 | 0 |
| 2006 | 771 | 546 | 184 | 0 |
| 2007 | 787 | 536 | 206 | 0 |
| 2008 | 772 | 548 | 333 | 0 |
| 2009 | 769 | 575 | 389 | 0 |
| 2010 | 785 | 626 | 415 | 0 |
| 2011 | 801 | 648 | 438 | 0 |
| 2012 | 796 | 662 | 445 | 163 |
| 2013 | 825 | 671 | 446 | 188 |
| 2014 | 867 | 660 | 468 | 208 |
| 2015 | 860 | 656 | 486 | 295 |
| 2016 | 854 | 648 | 492 | 321 |
| 2017 | 838 | 622 | 488 | 328 |
| 2018 | 830 | 615 | 476 | 324 |
| 2019 | 795 | 592 | 434 | 298 |
| 2020 | 839 | 565 | 409 | 282 |
| 2021 | 841 | 538 | 401 | 279 |
| 2022 | 743 | 510 | 372 | 277 |
| 2023 | 673 | 489 | 339 | 262 |
| 2024 | 631 | 471 | 329 | 254 |
| 2025 | 562 | 461 | 320 | 244 |
