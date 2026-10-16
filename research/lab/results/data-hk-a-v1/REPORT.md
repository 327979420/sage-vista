# data-hk-a-v1

Engineering check written by the research lab on 2026-10-16; no returns are computed. Every number comes from `result.json` in this folder.

## The question

Freeze HK exam group A (half of the 881 stocks kept by data-hk-universe-v1, split with seed 20261017; group B research/lab/universes/hk-exam-b-v1.txt stays locked) plus the Tracker Fund of Hong Kong (2800) as the market proxy, as a dataset with daily history from 1995 and the unadjusted close, and report how much history each year has. (Engineering check: no returns.)

## The short answer

- Built 442 of 442 symbols (0.0% missing); earliest bar 1995-01-03. Check passed: **yes**.

## History available at the start of each year

| Year | Trading | ≥50 months | ≥120 months | ≥200 months (monthly EMA200) |
|---|---|---|---|---|
| 2005 | 196 | 132 | 43 | 0 |
| 2006 | 212 | 142 | 44 | 0 |
| 2007 | 233 | 154 | 58 | 0 |
| 2008 | 241 | 164 | 67 | 0 |
| 2009 | 263 | 181 | 71 | 0 |
| 2010 | 290 | 194 | 120 | 0 |
| 2011 | 301 | 210 | 133 | 0 |
| 2012 | 306 | 229 | 146 | 43 |
| 2013 | 321 | 241 | 156 | 47 |
| 2014 | 341 | 261 | 165 | 63 |
| 2015 | 349 | 287 | 182 | 69 |
| 2016 | 356 | 298 | 197 | 71 |
| 2017 | 363 | 305 | 212 | 126 |
| 2018 | 374 | 314 | 233 | 138 |
| 2019 | 381 | 330 | 240 | 147 |
| 2020 | 391 | 336 | 258 | 155 |
| 2021 | 391 | 331 | 271 | 159 |
| 2022 | 380 | 321 | 265 | 158 |
| 2023 | 389 | 330 | 268 | 171 |
| 2024 | 390 | 337 | 277 | 182 |
| 2025 | 383 | 343 | 290 | 198 |
