# data-fresh-a-v1

Engineering check written by the research lab on 2026-10-13; no returns are computed. Every number comes from `result.json` in this folder.

## The question

Freeze shard a of the wider universe (1500 US stocks no rule has seen, from data-fresh-universe-v2) as a dataset with daily history from 1995 and the unadjusted close, and report how much history each year has. (Engineering check: no returns.)

## The short answer

- Built 1500 of 1500 symbols (0.0% missing); earliest bar 1995-01-02. Check passed: **yes**.

## History available at the start of each year

| Year | Trading | ≥50 months | ≥120 months | ≥200 months (monthly EMA200) |
|---|---|---|---|---|
| 2005 | 767 | 583 | 182 | 0 |
| 2006 | 805 | 604 | 210 | 0 |
| 2007 | 823 | 612 | 230 | 0 |
| 2008 | 799 | 622 | 384 | 0 |
| 2009 | 794 | 631 | 431 | 0 |
| 2010 | 807 | 655 | 459 | 0 |
| 2011 | 810 | 678 | 486 | 0 |
| 2012 | 807 | 692 | 492 | 189 |
| 2013 | 831 | 684 | 498 | 217 |
| 2014 | 866 | 683 | 522 | 229 |
| 2015 | 883 | 686 | 533 | 335 |
| 2016 | 882 | 674 | 537 | 361 |
| 2017 | 864 | 643 | 532 | 356 |
| 2018 | 853 | 640 | 525 | 355 |
| 2019 | 820 | 633 | 479 | 344 |
| 2020 | 858 | 611 | 451 | 324 |
| 2021 | 866 | 570 | 417 | 308 |
| 2022 | 775 | 525 | 376 | 289 |
| 2023 | 700 | 502 | 345 | 271 |
| 2024 | 633 | 469 | 331 | 258 |
| 2025 | 573 | 468 | 325 | 245 |
