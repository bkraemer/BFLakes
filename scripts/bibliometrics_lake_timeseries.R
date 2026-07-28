# Bibliometric time series: Black Forest lakes vs. well-funded German research lakes
# Adapted from CODE_aquatic_bibliometrics_openalex_v1.R.
#
# Question: over the last ~30 years, has scientific attention to the Black
# Forest lakes stayed flat/low while comparable German lakes with dedicated
# research infrastructure kept growing?
#
# Comparison lakes (all have a major limnological institute/long-term
# monitoring program attached):
#   - Müggelsee    -> IGB Berlin
#   - Bodensee (Lake Constance) -> Limnological Institute, University of
#     Konstanz -- the institute Hans-Joachim Elster's group relocated to
#     found in 1970, after leading the Black Forest's own Falkau station
#     from 1948.
#   - Stechlinsee  -> IGB's flagship oligotrophic long-term-research lake
#   - Plußsee      -> historic Max Planck Institute for Limnology (Plön) site
#   - Chiemsee     -> large, heavily monitored Bavarian lake
#
# Counts are binned into 5-year periods (not annual) because several Black
# Forest lakes likely have single-digit-or-zero papers in any given year --
# annual resolution would be mostly noise. Change `bin_width` below for
# annual or a different bin size.
#
# Run this locally (needs normal internet access -- OpenAlex is blocked from
# the sandbox this was written in). Send back lake_bibliometric_timeseries.csv.

install.packages(c("data.table", "jsonlite", "stringr", "ggplot2", "scales", "httr"))

library(data.table)
library(jsonlite)
library(stringr)
library(ggplot2)
library(scales)

# ---- Settings ---------------------------------------------------------------

Sys.setenv(OPENALEX_MAILTO = "ben.m.kraemer@gmail.com")
# Sys.setenv(OPENALEX_API_KEY = "YOUR_KEY")

start_year <- 1996
end_year <- 2025
bin_width <- 5   # years per bin; set to 1 for annual (much noisier, more queries)

cache_file <- "lake_bibliometric_timeseries_cache.rds"
csv_file <- "lake_bibliometric_timeseries.csv"
plot_file <- "lake_bibliometric_timeseries.png"

# 14 Black Forest study lakes -- name + disambiguating qualifier, same logic
# as the earlier bibliometrics_lake_coverage.R (several names collide with
# towns/other lakes of the same name elsewhere in Germany).
black_forest_lakes <- data.table(
  lake = c(
    "Nonnenmattweiher", "Feldsee", "Titisee", "Schluchsee", "Windgfällweiher",
    "Blindensee", "Glaswaldsee", "Sankenbachsee", "Schurmsee",
    "Wildsee (Kaltenbronn)", "Wilder See (Ruhestein)", "Großer Hohlohsee",
    "Mummelsee", "Herrenwieser See"
  ),
  search_name = c(
    "Nonnenmattweiher", "Feldsee", "Titisee", "Schluchsee", "Windgfällweiher",
    "Blindensee", "Glaswaldsee", "Sankenbachsee", "Schurmsee",
    "Wildsee", "\"Wilder See\"", "\"Großer Hohlohsee\"",
    "Mummelsee", "\"Herrenwieser See\""
  ),
  qualifier = c(
    'Schwarzwald OR "Black Forest"', 'Schwarzwald OR "Black Forest"',
    'Schwarzwald OR "Black Forest"', 'Schwarzwald OR "Black Forest"',
    'Schwarzwald OR "Black Forest"', 'Schwarzwald OR "Black Forest"',
    'Schwarzwald OR "Black Forest"', 'Schwarzwald OR "Black Forest"',
    'Schwarzwald OR "Black Forest"',
    'Kaltenbronn',
    'Ruhestein OR Hornisgrinde',
    'Kaltenbronn OR Schwarzwald',
    'Schwarzwald OR "Black Forest"', 'Schwarzwald OR "Black Forest"'
  )
)

# 5 comparison lakes -- well-known names, low collision risk, so no
# additional regional qualifier needed (Bodensee/Lake Constance gets both
# the German and English name since it's written about internationally).
comparison_lakes <- data.table(
  lake = c("Müggelsee", "Bodensee (Lake Constance)", "Stechlinsee", "Plußsee", "Chiemsee"),
  search_name = c(
    "Müggelsee",
    '(Bodensee OR "Lake Constance")',
    '(Stechlinsee OR "Lake Stechlin")',
    '(Plußsee OR Plusssee)',
    "Chiemsee"
  ),
  qualifier = c(NA, NA, NA, NA, NA)
)

periods <- data.table(
  period_start = seq(start_year, end_year, by = bin_width)
)
periods[, period_end := pmin(period_start + bin_width - 1, end_year)]
periods[, period_label := paste0(period_start, "–", period_end)]

# ---- OpenAlex helpers -------------------------------------------------------
#
# Uses httr rather than base readLines()/file(): base R's URL reader sends a
# minimal, generic User-Agent with no way to attach one, which public APIs'
# bot-protection can flag long before any real rate limit is hit -- and on
# failure it only ever surfaces "HTTP status was 429", never the actual
# response body, so there's no way to tell a real quota problem from
# something else. httr fixes both: a proper identifying User-Agent (the
# mechanism OpenAlex's own docs describe for "polite pool" access), and the
# real error body printed on failure so we can actually diagnose it.

if (!requireNamespace("httr", quietly = TRUE)) install.packages("httr")
library(httr)

base_url <- "https://api.openalex.org"

oa_query <- function(...) {
  query <- list(...)
  api_key <- Sys.getenv("OPENALEX_API_KEY", unset = "")
  mailto <- Sys.getenv("OPENALEX_MAILTO", unset = "")
  if (nzchar(api_key)) query$api_key <- api_key
  if (nzchar(mailto)) query$mailto <- mailto
  query
}

oa_user_agent <- function() {
  mailto <- Sys.getenv("OPENALEX_MAILTO", unset = "")
  httr::user_agent(
    if (nzchar(mailto)) paste0("mailto:", mailto, " (BFLakes bibliometrics)")
    else "BFLakes bibliometrics script (no contact email set)"
  )
}

oa_get <- function(path, ..., max_tries = 7) {
  query <- oa_query(...)
  url <- paste0(base_url, path)

  for (try_i in seq_len(max_tries)) {
    resp <- tryCatch(
      httr::GET(url, query = query, oa_user_agent(), httr::timeout(30)),
      error = identity
    )

    if (inherits(resp, "error")) {
      wait <- min(90, 2 ^ try_i + runif(1, 0, 1))
      message("Connection error: ", conditionMessage(resp), " -- retrying in ", round(wait, 1), "s")
      Sys.sleep(wait)
      next
    }

    status <- httr::status_code(resp)

    if (status == 200) {
      txt <- httr::content(resp, as = "text", encoding = "UTF-8")
      return(jsonlite::fromJSON(txt, simplifyVector = FALSE))
    }

    if (status == 429 || status >= 500) {
      body <- tryCatch(httr::content(resp, as = "text", encoding = "UTF-8"), error = function(e) "")
      retry_after <- suppressWarnings(as.numeric(httr::headers(resp)[["retry-after"]]))
      wait <- if (!is.na(retry_after)) retry_after else min(90, 2 ^ try_i + runif(1, 0, 5))
      message(
        "HTTP ", status, " (attempt ", try_i, "/", max_tries, "). Body: ",
        substr(body, 1, 300), " -- retrying in ", round(wait, 1), "s"
      )
      Sys.sleep(wait)
      next
    }

    # Non-retryable 4xx: fail loudly and immediately, with the real response body.
    body <- tryCatch(httr::content(resp, as = "text", encoding = "UTF-8"), error = function(e) "")
    stop("OpenAlex request failed with HTTP ", status, ": ", body, "\nURL: ", url)
  }
  stop("OpenAlex request failed after ", max_tries, " tries: ", url)
}

count_works <- function(search_expr, year_start, year_end) {
  # Use the documented >/< comparator filters rather than an undocumented
  # "YYYY-YYYY" range string, which OpenAlex may not parse as intended.
  year_filter <- if (year_start == year_end) {
    paste0("publication_year:", year_start)
  } else {
    paste0("publication_year:>", year_start - 1, ",publication_year:<", year_end + 1)
  }
  res <- oa_get(
    "/works",
    filter = paste0("title_and_abstract.search:", search_expr, ",", year_filter),
    per_page = 1
  )
  res$meta$count %||% 0L
}

`%||%` <- function(x, y) if (is.null(x) || length(x) == 0) y else x

# ---- Query every (lake, period) combination ---------------------------------

all_lakes <- rbindlist(list(
  black_forest_lakes[, group := "Black Forest (individual lake)"],
  comparison_lakes[, group := "Comparison lake"]
))

# Incremental, resumable: saves after every single query, and skips any
# (lake, period) pair already present in the cache on a rerun. If the script
# dies partway through (network hiccup, rate limit, anything), rerunning it
# picks up exactly where it left off instead of losing all prior progress.

jobs <- CJ(lake_i = seq_len(nrow(all_lakes)), period_i = seq_len(nrow(periods)))

raw_results <- if (file.exists(cache_file)) {
  message("Resuming from cached counts: ", cache_file)
  readRDS(cache_file)
} else {
  data.table(
    lake = character(), group = character(),
    period_start = integer(), period_end = integer(), period_label = character(),
    n_papers = integer()
  )
}

for (j in seq_len(nrow(jobs))) {
  li <- jobs$lake_i[j]
  pi <- jobs$period_i[j]

  already_done <- raw_results[
    lake == all_lakes$lake[li] & period_start == periods$period_start[pi], .N
  ] > 0
  if (already_done) next

  expr <- all_lakes$search_name[li]
  if (!is.na(all_lakes$qualifier[li])) {
    expr <- paste0(expr, " AND (", all_lakes$qualifier[li], ")")
  }

  message(
    all_lakes$lake[li], " / ", periods$period_label[pi],
    " (", j, "/", nrow(jobs), ")"
  )

  n <- count_works(expr, periods$period_start[pi], periods$period_end[pi])
  Sys.sleep(0.15)

  raw_results <- rbindlist(list(raw_results, data.table(
    lake = all_lakes$lake[li],
    group = all_lakes$group[li],
    period_start = periods$period_start[pi],
    period_end = periods$period_end[pi],
    period_label = periods$period_label[pi],
    n_papers = n
  )))

  saveRDS(raw_results, cache_file)
}

fwrite(raw_results, "lake_bibliometric_timeseries_by_lake.csv")

# Aggregate the 14 Black Forest lakes into one series per period.
# NOTE: if a single paper happened to mention two of the 14 lakes, it would
# be counted twice here. Given how narrow each lake's individual count is
# expected to be, this is a minor, disclosed limitation, not deduplicated.
bf_series <- raw_results[
  group == "Black Forest (individual lake)",
  .(lake = "Black Forest lakes (14 combined)", group = "Black Forest (14 lakes, summed)",
    n_papers = sum(n_papers)),
  by = .(period_start, period_end, period_label)
]

comparison_series <- raw_results[group == "Comparison lake"]

series <- rbindlist(list(bf_series, comparison_series), fill = TRUE)
setorder(series, lake, period_start)
fwrite(series, csv_file)
print(series)

# ---- Plot --------------------------------------------------------------------

series[, lake := factor(lake, levels = c(
  "Black Forest lakes (14 combined)", "Müggelsee",
  "Bodensee (Lake Constance)", "Stechlinsee", "Plußsee", "Chiemsee"
))]

# This exact 6-hue order (blue, orange, aqua, yellow, magenta, green) is a
# validated colorblind-safe categorical sequence -- do not reorder which
# color maps to which series without re-validating.
line_cols <- c(
  "Black Forest lakes (14 combined)" = "#2a78d6",
  "Müggelsee"                        = "#eb6834",
  "Bodensee (Lake Constance)"        = "#1baf7a",
  "Stechlinsee"                      = "#eda100",
  "Plußsee"                          = "#e87ba4",
  "Chiemsee"                         = "#008300"
)
line_widths <- c(
  "Black Forest lakes (14 combined)" = 2.4,
  "Müggelsee" = 1.2, "Bodensee (Lake Constance)" = 1.2,
  "Stechlinsee" = 1.2, "Plußsee" = 1.2, "Chiemsee" = 1.2
)

caption_txt <- str_wrap(paste0(
  "Data: OpenAlex, queried ", Sys.Date(), ". Counts are OpenAlex works whose title/abstract ",
  "mention the lake name (plus a disambiguating regional term for Black Forest lakes with ",
  "common names). Black Forest series is the sum of 14 individual lake queries per period; ",
  "see lake_bibliometric_timeseries_by_lake.csv for the per-lake breakdown."
), width = 100)

p <- ggplot(series, aes(period_start, n_papers, color = lake, linewidth = lake)) +
  geom_line(alpha = 0.9) +
  geom_point(size = 2.6, show.legend = FALSE) +
  scale_color_manual(values = line_cols) +
  scale_linewidth_manual(values = line_widths, guide = "none") +
  scale_y_continuous(labels = label_number(accuracy = 1)) +
  scale_x_continuous(breaks = periods$period_start, labels = periods$period_label) +
  labs(
    title = "Scientific attention to Black Forest lakes vs. well-funded German research lakes",
    subtitle = paste0("Papers mentioning each lake by name, ", start_year, "–", end_year, ", in ", bin_width, "-year bins"),
    x = NULL,
    y = "Papers per period",
    color = NULL,
    caption = caption_txt
  ) +
  theme_minimal(base_family = "sans", base_size = 15) +
  theme(
    plot.background = element_rect(fill = "#FAF9F6", color = NA),
    panel.background = element_rect(fill = "#FAF9F6", color = NA),
    panel.grid.minor = element_blank(),
    panel.grid.major.x = element_blank(),
    axis.text.x = element_text(angle = 45, hjust = 1),
    plot.title = element_text(face = "bold", size = 19, color = "#202020", margin = margin(b = 6)),
    plot.subtitle = element_text(size = 13.5, color = "#4B4B4B", margin = margin(b = 16)),
    plot.caption = element_text(size = 10, color = "#5A5A5A", hjust = 0, lineheight = 1.1, margin = margin(t = 16)),
    legend.position = "top",
    legend.justification = "left",
    plot.margin = margin(20, 30, 20, 20)
  )

ggsave(plot_file, p, width = 11, height = 8, dpi = 320, bg = "#FAF9F6")

message("Saved: ", normalizePath(csv_file))
message("Saved: ", normalizePath("lake_bibliometric_timeseries_by_lake.csv"))
message("Saved: ", normalizePath(plot_file))
