# Bibliometric coverage of Black Forest lakes vs. comparable German lakes
# Adapted from CODE_aquatic_bibliometrics_openalex_v1.R.
#
# Instead of counting term mentions within fixed journals, this counts how
# many OpenAlex works (any source, any year) mention each lake by name in
# their title or abstract -- a direct measure of how much scientific
# literature exists about that specific place.
#
# Comparison lakes were chosen for similar size, similar protection status
# (Naturschutzgebiet), and similar origin (glacial cirque lake / raised-bog
# lake), but located outside the Black Forest, within Germany:
#   - Kleiner Arbersee, Grosser Arbersee (Bavarian Forest) -> cirque-lake comparison
#   - Grosser Ursee, Kleiner Ursee (Allguu, Bodenmoeser NSG) -> bog-lake comparison
#
# Run this locally (needs normal internet access -- OpenAlex is blocked from
# the sandbox this was written in). Sends back lake_bibliometric_counts.csv;
# paste/upload that back and the figure gets built from these real numbers.

install.packages(c("data.table", "jsonlite", "stringr", "ggplot2", "scales"))

library(data.table)
library(jsonlite)
library(stringr)
library(ggplot2)
library(scales)

# ---- Settings ---------------------------------------------------------------

# Use your own OpenAlex API key if you have one:
# Sys.setenv(OPENALEX_API_KEY = "YOUR_KEY")
# Optional, but useful for polite API contact:
Sys.setenv(OPENALEX_MAILTO = "ben.m.kraemer@gmail.com")

cache_file <- "lake_bibliometric_counts_cache.rds"
csv_file <- "lake_bibliometric_counts.csv"
plot_file <- "lake_bibliometric_coverage.png"

lakes <- data.table(
  lake = c(
    "Nonnenmattweiher", "Feldsee", "Titisee", "Schluchsee", "Windgfällweiher",
    "Blindensee", "Glaswaldsee", "Sankenbachsee", "Schurmsee",
    "Wildsee (Kaltenbronn)", "Wilder See (Ruhestein)", "Großer Hohlohsee",
    "Mummelsee", "Herrenwieser See",
    "Kleiner Arbersee", "Großer Arbersee", "Großer Ursee", "Kleiner Ursee"
  ),
  search_name = c(
    "Nonnenmattweiher", "Feldsee", "Titisee", "Schluchsee", "Windgfällweiher",
    "Blindensee", "Glaswaldsee", "Sankenbachsee", "Schurmsee",
    "Wildsee", "\"Wilder See\"", "\"Großer Hohlohsee\"",
    "Mummelsee", "\"Herrenwieser See\"",
    "\"Kleiner Arbersee\"", "\"Großer Arbersee\"", "\"Großer Ursee\"", "\"Kleiner Ursee\""
  ),
  # Disambiguating qualifier required alongside the name -- several of these
  # names are shared with towns, hotels, or other lakes of the same name
  # elsewhere in Germany (e.g. there is a second "Wildsee" in the Allgäu).
  qualifier = c(
    'Schwarzwald OR "Black Forest"', 'Schwarzwald OR "Black Forest"',
    'Schwarzwald OR "Black Forest"', 'Schwarzwald OR "Black Forest"',
    'Schwarzwald OR "Black Forest"', 'Schwarzwald OR "Black Forest"',
    'Schwarzwald OR "Black Forest"', 'Schwarzwald OR "Black Forest"',
    'Schwarzwald OR "Black Forest"',
    'Kaltenbronn',
    'Ruhestein OR Hornisgrinde',
    'Kaltenbronn OR Schwarzwald',
    'Schwarzwald OR "Black Forest"', 'Schwarzwald OR "Black Forest"',
    '"Bayerischer Wald" OR "Bavarian Forest"', '"Bayerischer Wald" OR "Bavarian Forest"',
    'Allgäu OR Bodenmöser', 'Allgäu OR Bodenmöser'
  ),
  group = c(
    rep("Black Forest lake (this study)", 14),
    rep("Comparison: other protected German lake", 4)
  )
)

# ---- OpenAlex helpers (reused from the original script) --------------------

base_url <- "https://api.openalex.org"

oa_query <- function(...) {
  query <- list(...)
  api_key <- Sys.getenv("OPENALEX_API_KEY", unset = "")
  mailto <- Sys.getenv("OPENALEX_MAILTO", unset = "")
  if (nzchar(api_key)) query$api_key <- api_key
  if (nzchar(mailto)) query$mailto <- mailto
  query
}

make_url <- function(path, query) {
  query <- lapply(query, as.character)
  query_string <- paste(
    paste0(
      utils::URLencode(names(query), reserved = TRUE),
      "=",
      vapply(query, utils::URLencode, character(1), reserved = TRUE)
    ),
    collapse = "&"
  )
  paste0(base_url, path, "?", query_string)
}

oa_get <- function(path, ..., max_tries = 7) {
  query <- oa_query(...)
  url <- make_url(path, query)

  for (try_i in seq_len(max_tries)) {
    txt <- tryCatch(
      paste(readLines(url, warn = FALSE), collapse = "\n"),
      error = identity
    )
    if (!inherits(txt, "error")) {
      return(fromJSON(txt, simplifyVector = FALSE))
    }
    wait <- min(90, 2 ^ try_i + runif(1, 0, 1))
    message("OpenAlex request failed; retrying in ", round(wait, 1), " seconds.")
    Sys.sleep(wait)
  }
  stop("OpenAlex request failed after ", max_tries, " tries: ", url)
}

# ---- Query: how many works mention each lake, with and without the ----------
# ---- disambiguating qualifier -----------------------------------------------

count_works <- function(search_expr) {
  res <- oa_get(
    "/works",
    filter = paste0("title_and_abstract.search:", search_expr),
    per_page = 1
  )
  res$meta$count %||% 0L
}

`%||%` <- function(x, y) if (is.null(x) || length(x) == 0) y else x

if (file.exists(cache_file)) {
  message("Using cached counts: ", cache_file)
  results <- readRDS(cache_file)
} else {
  results <- rbindlist(lapply(seq_len(nrow(lakes)), function(i) {
    message("Querying: ", lakes$lake[i])

    n_qualified <- count_works(
      paste0(lakes$search_name[i], " AND (", lakes$qualifier[i], ")")
    )
    Sys.sleep(0.2)
    n_raw <- count_works(lakes$search_name[i])
    Sys.sleep(0.2)

    data.table(
      lake = lakes$lake[i],
      group = lakes$group[i],
      n_papers_qualified = n_qualified,   # name + regional qualifier (primary, conservative)
      n_papers_raw = n_raw                # name alone (upper bound, may include homonyms)
    )
  }))
  saveRDS(results, cache_file)
}

setorder(results, group, -n_papers_qualified)
fwrite(results, csv_file)
print(results)

# ---- Plot --------------------------------------------------------------------

results[, lake := factor(lake, levels = rev(lake))]

p <- ggplot(results, aes(x = lake, y = n_papers_qualified, fill = group)) +
  geom_col(width = 0.72) +
  geom_text(aes(label = n_papers_qualified), hjust = -0.3, size = 4.2, color = "#202020") +
  coord_flip(clip = "off") +
  scale_fill_manual(values = c(
    "Black Forest lake (this study)" = "#2f6b4f",
    "Comparison: other protected German lake" = "#3d6e8f"
  )) +
  scale_y_continuous(expand = expansion(mult = c(0, 0.18))) +
  labs(
    title = "How much has science studied these lakes?",
    subtitle = "OpenAlex works mentioning each lake by name in title/abstract (all years, all sources)",
    x = NULL,
    y = "Papers mentioning this lake",
    fill = NULL,
    caption = str_wrap(
      paste0(
        "Data: OpenAlex, queried ", Sys.Date(), ". Counts require the lake name plus a ",
        "disambiguating regional term (e.g. 'Schwarzwald'), since several names are shared ",
        "with towns, hotels, or lakes of the same name elsewhere in Germany -- see n_papers_raw ",
        "in the CSV for the unqualified (upper-bound) count."
      ),
      width = 100
    )
  ) +
  theme_minimal(base_family = "sans", base_size = 15) +
  theme(
    plot.background = element_rect(fill = "#FAF9F6", color = NA),
    panel.background = element_rect(fill = "#FAF9F6", color = NA),
    panel.grid.minor = element_blank(),
    panel.grid.major.y = element_blank(),
    plot.title = element_text(face = "bold", size = 22, color = "#202020"),
    plot.subtitle = element_text(size = 13.5, color = "#4B4B4B", margin = margin(b = 14)),
    plot.caption = element_text(size = 10, color = "#5A5A5A", hjust = 0, lineheight = 1.1, margin = margin(t = 16)),
    axis.text.y = element_text(size = 12.5),
    legend.position = "top",
    legend.justification = "left",
    plot.margin = margin(20, 40, 20, 20)
  )

ggsave(plot_file, p, width = 10, height = 8.5, dpi = 320, bg = "#FAF9F6")

message("Saved: ", normalizePath(csv_file))
message("Saved: ", normalizePath(plot_file))
