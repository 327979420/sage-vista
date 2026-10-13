# data-fresh-c-v1

Engineering check written by the research lab on 2026-10-13; no returns are computed. Every number comes from `result.json` in this folder.

## The question

Freeze shard c of the wider universe (1500 US stocks no rule has seen, from data-fresh-universe-v2) as a dataset with daily history from 1995 and the unadjusted close, and report how much history each year has. (Engineering check: no returns.)

## The short answer

- Built 1500 of 1500 symbols (0.0% missing); earliest bar 1995-01-03. Check passed: **yes**.

## History available at the start of each year

| Year | Trading | ≥50 months | ≥120 months | ≥200 months (monthly EMA200) |
|---|---|---|---|---|
| 2005 | 754 | 558 | 176 | 0 |
| 2006 | 777 | 573 | 199 | 0 |
| 2007 | 801 | 581 | 217 | 0 |
| 2008 | 777 | 595 | 372 | 0 |
| 2009 | 771 | 622 | 416 | 0 |
| 2010 | 790 | 641 | 440 | 0 |
| 2011 | 802 | 654 | 469 | 0 |
| 2012 | 811 | 671 | 468 | 182 |
| 2013 | 838 | 665 | 474 | 201 |
| 2014 | 879 | 654 | 493 | 215 |
| 2015 | 903 | 677 | 524 | 326 |
| 2016 | 890 | 667 | 515 | 338 |
| 2017 | 852 | 632 | 497 | 337 |
| 2018 | 833 | 643 | 498 | 341 |
| 2019 | 811 | 634 | 460 | 327 |
| 2020 | 874 | 624 | 437 | 312 |
| 2021 | 888 | 592 | 421 | 310 |
| 2022 | 792 | 556 | 396 | 309 |
| 2023 | 718 | 514 | 363 | 285 |
| 2024 | 656 | 484 | 357 | 267 |
| 2025 | 603 | 500 | 353 | 263 |
