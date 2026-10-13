# data-fresh-d-v1

Engineering check written by the research lab on 2026-10-13; no returns are computed. Every number comes from `result.json` in this folder.

## The question

Freeze shard d of the wider universe (1000 US stocks no rule has seen, from data-fresh-universe-v2) as a dataset with daily history from 1995 and the unadjusted close, and report how much history each year has. (Engineering check: no returns.)

## The short answer

- Built 1000 of 1000 symbols (0.0% missing); earliest bar 1995-01-03. Check passed: **yes**.

## History available at the start of each year

| Year | Trading | ≥50 months | ≥120 months | ≥200 months (monthly EMA200) |
|---|---|---|---|---|
| 2005 | 488 | 359 | 131 | 0 |
| 2006 | 501 | 362 | 139 | 0 |
| 2007 | 518 | 368 | 155 | 0 |
| 2008 | 502 | 379 | 234 | 0 |
| 2009 | 501 | 394 | 266 | 0 |
| 2010 | 515 | 419 | 287 | 0 |
| 2011 | 532 | 434 | 307 | 0 |
| 2012 | 541 | 442 | 306 | 132 |
| 2013 | 563 | 437 | 309 | 144 |
| 2014 | 596 | 425 | 323 | 156 |
| 2015 | 604 | 424 | 318 | 206 |
| 2016 | 603 | 431 | 329 | 220 |
| 2017 | 597 | 431 | 326 | 226 |
| 2018 | 575 | 420 | 317 | 223 |
| 2019 | 551 | 418 | 290 | 211 |
| 2020 | 576 | 412 | 274 | 205 |
| 2021 | 576 | 384 | 256 | 195 |
| 2022 | 501 | 364 | 240 | 179 |
| 2023 | 439 | 332 | 221 | 168 |
| 2024 | 402 | 314 | 214 | 164 |
| 2025 | 369 | 311 | 217 | 154 |
