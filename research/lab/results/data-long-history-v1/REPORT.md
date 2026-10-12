# data-long-history-v1

Engineering check written by the research lab on 2026-10-12; no returns are computed. Every number comes from `result.json` in this folder.

## The question

Build the long-history price dataset the monthly-led buy system needs (the 1,223 stocks of the 20-year observation set plus the reviewed-case stocks it lacks, adjusted daily bars from 1985) and report, for every year 2005-2025, how many stocks had 50, 120 and 200 months of history (monthly EMA200 needs about 200), and how much history each reviewed case had on its date. Engineering check only; no returns are computed.

## The short answer

- Built 1228 of 1228 symbols (0.0% missing); earliest bar 1985-01-02. Check passed: **yes**.

## History available at the start of each year

| Year | Trading | ≥50 months | ≥120 months | ≥200 months (monthly EMA200) |
|---|---|---|---|---|
| 2005 | 827 | 713 | 528 | 381 |
| 2006 | 858 | 739 | 569 | 386 |
| 2007 | 885 | 759 | 595 | 401 |
| 2008 | 902 | 773 | 631 | 414 |
| 2009 | 909 | 802 | 653 | 442 |
| 2010 | 943 | 825 | 684 | 475 |
| 2011 | 960 | 856 | 715 | 514 |
| 2012 | 989 | 880 | 741 | 535 |
| 2013 | 1024 | 901 | 763 | 574 |
| 2014 | 1061 | 908 | 775 | 606 |
| 2015 | 1103 | 940 | 803 | 638 |
| 2016 | 1128 | 958 | 827 | 661 |
| 2017 | 1152 | 986 | 859 | 693 |
| 2018 | 1188 | 1020 | 884 | 716 |
| 2019 | 1214 | 1056 | 899 | 744 |
| 2020 | 1223 | 1101 | 908 | 763 |
| 2021 | 1225 | 1127 | 941 | 783 |
| 2022 | 1224 | 1149 | 960 | 807 |
| 2023 | 1224 | 1183 | 987 | 840 |
| 2024 | 1224 | 1210 | 1023 | 869 |
| 2025 | 1224 | 1222 | 1063 | 892 |

## Reviewed cases

| Case | Date | First bar | Months before | Monthly EMA200 ready |
|---|---|---|---|---|
| MGY | 2024-04-17 | 2017-06-29 | 82 | no |
| HUBB | 2019-05-21 | 1985-01-02 | 412 | yes |
| SHEL | 2006-05-30 | 1985-01-02 | 256 | yes |
| ZBH | 2007-05-14 | 2001-07-25 | 70 | no |
| AVTR | 2024-08-01 | 2019-05-16 | 63 | no |
| TT | 2009-07-17 | 1985-01-02 | 294 | yes |
| DLR | 2009-11-04 | 2004-10-29 | 61 | no |
| QTWO | 2020-07-13 | 2014-03-20 | 76 | no |
| YPF | 2012-02-10 | 1993-06-29 | 224 | yes |
| COLB | 2019-03-14 | 1992-06-16 | 321 | yes |
| DVN | 2012-04-02 | 1985-07-22 | 321 | yes |
| EIX | 2021-01-07 | 1985-01-02 | 432 | yes |
| TT | 2009-03-31 | 1985-01-02 | 290 | yes |
| AVTR | 2023-11-30 | 2019-05-16 | 54 | no |
| COLB | 2019-05-31 | 1992-06-16 | 323 | yes |
| DVN | 2013-01-31 | 1985-07-22 | 330 | yes |
| AXSM | 2022-10-31 | 2015-11-19 | 83 | no |
| VICR | 2025-04-30 | 1990-04-03 | 420 | yes |
| BABA | 2025-07-14 | 2014-09-18 | 130 | no |
| PG | 2026-10-09 | 1985-01-02 | 501 | yes |
| ADBE | 2023-05-18 | 1986-08-13 | 441 | yes |
| TTD | 2025-01-17 | 2016-09-21 | 100 | no |
| AEVA | 2026-07-01 | 2020-02-27 | 77 | no |
| MRNA | 2024-04-24 | 2018-12-07 | 64 | no |
| BTDR | 2024-03-15 | 2021-07-28 | 32 | no |
| CGEM | 2024-04-17 | 2021-01-08 | 39 | no |
| DLTR | 2024-04-01 | 1995-03-07 | 349 | yes |
