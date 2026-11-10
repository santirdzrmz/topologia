## -----------------------------------------------------------------------
## simulate_topodata.R
##
## Generates fictitious "Maestro" (vendor master) and "Pagos" (payments)
## tables with the same schema as the real exports, but with structure
## deliberately embedded for topological / descriptive analysis demos:
##
##   - CLUSTERS   -> vendor archetypes with distinct joint distributions
##                   over payment terms, amounts, tax regime, etc.
##   - MANIFOLD   -> a continuous latent "size" factor drives several
##                   correlated observed variables non-linearly
##   - CYCLES     -> each vendor pays on an approximately periodic
##                   cadence (with jitter) -> should show up as loops
##                   (H1 features) under a time-delay / Mapper embedding
##   - OUTLIERS   -> a vendor-level archetype ("OUTLIER") plus sporadic
##                   anomalous payments injected into normal vendors
##   - STRUCTURED MISSINGNESS -> NAs conditioned on vendor type / method,
##                   as seen in the real sample (not MCAR)
##   - REFERENTIAL INTEGRITY  -> vendor_id, site, and bank account are
##                   shared between the two tables
##
## Output: two CSVs under ./simulated_data/
## -----------------------------------------------------------------------

library(dplyr)
library(purrr)
library(tidyr)
library(stringr)
library(lubridate)
library(tibble)

SEED        <- 8347
N_VENDORS   <- 400
DATE_RANGE  <- as.Date(c("2023-01-01", "2025-12-31"))
OUT_DIR     <- "simulated_data"

set.seed(SEED)
dir.create(OUT_DIR, showWarnings = FALSE)

## ------------------------------------------------------------------
## 1. Vendor archetypes (clusters)
## ------------------------------------------------------------------
archetypes <- tribble(
  ~tipo_proveedor,     ~weight, ~size_mean_log, ~size_sd_log, ~terminos_dias, ~ciclo_dias, ~ciclo_jitter, ~n_pagos_mean, ~metodo_pago, ~moneda,
  "COMERCIALIZADORES", 0.30,    10.8,           0.45,         45,             30,          4,             10,            "TRANSFER",   "MXN",
  "SERVICIOS",         0.28,    9.3,            0.55,         30,             14,          2,             16,            "TRANSFER",   "MXN",
  "TRANSPORTISTAS",    0.20,    10.3,           0.45,         15,             7,           1.5,           26,            "TRANSFER",   "MXN",
  "IMPORTADORES",      0.19,    12.3,           0.60,         75,             90,          10,            6,             "TRANSFER",   "USD",
  "OUTLIER",           0.03,    12.8,           1.30,         20,             NA,          NA,            5,             "CHEQUE",     "MXN"
)

sites <- tribble(
  ~unidad_operativa,                     ~site,    ~estado,
  "20MTY - PL_MONTERREY_CCO_UO",         "20MTY",  "NUEVO LEON",
  "27MTY - PL_MONTERREY_CEDIS_UO",       "27MTY",  "NUEVO LEON",
  "30GDL - PL_GUADALAJARA_CCO_UO",       "30GDL",  "JALISCO",
  "10CDMX - PL_CDMX_CCO_UO",             "10CDMX", "CIUDAD DE MEXICO",
  "40QRO - PL_QUERETARO_CCO_UO",         "40QRO",  "QUERETARO",
  "50TIJ - PL_TIJUANA_CCO_UO",           "50TIJ",  "BAJA CALIFORNIA"
)

word_root  <- c("EJEMPLO","FICTICIA","DEMO","MODELO","PRUEBA","SIMULADA","GENERICA","REFERENCIA")
word_theme <- c("DEL NORTE","DE OCCIDENTE","INDUSTRIAL","LOGISTICA","COMERCIAL","NACIONAL","INTEGRAL","DEL BAJIO")
legal_suf  <- c("S.A. DE C.V.", "S. DE R.L. DE C.V.")

rand_rfc <- function(n) {
  letters4 <- replicate(n, paste0(sample(LETTERS, 4), collapse = ""))
  digits6  <- sprintf("%06d", sample(10000:999999, n))
  alnum3   <- replicate(n, paste0(sample(c(LETTERS, 0:9), 3), collapse = ""))
  paste0(letters4, digits6, alnum3)
}

rand_date_str <- function(dates) format(dates, "%d-%b-%y")  # e.g. 15-Jan-20

## ------------------------------------------------------------------
## 2. Simulate vendors (Maestro)
## ------------------------------------------------------------------
cluster_idx <- sample(nrow(archetypes), N_VENDORS, replace = TRUE, prob = archetypes$weight)
arche       <- archetypes[cluster_idx, ]
site_idx    <- sample(nrow(sites), N_VENDORS, replace = TRUE)
site_info   <- sites[site_idx, ]

# Latent manifold factor: continuous "size" drives several correlated,
# non-linearly transformed observed variables below.
log_size    <- rnorm(N_VENDORS, mean = arche$size_mean_log, sd = arche$size_sd_log)
size_factor <- exp(log_size)
risk_score  <- plogis(rnorm(N_VENDORS, 0, 1) - 0.4 * scale(log_size)[, 1])

vendor_id    <- sample(5000:99999, N_VENDORS)
bank_account <- str_pad(sample(1e11:(1e12 - 1), N_VENDORS), 18, pad = "0")
creacion     <- DATE_RANGE[1] - days(sample(30:2500, N_VENDORS, replace = TRUE))
actualiza    <- creacion + days(sample(30:900, N_VENDORS, replace = TRUE))

maestro <- tibble(
  `Unidad Operativa`       = site_info$unidad_operativa,
  `Id Proveedor`           = vendor_id,
  `Tipo Proveedor`         = arche$tipo_proveedor,
  `Nombre Proveedor`       = sprintf(
    "%s %s DE %s, %s",
    c("COMERCIALIZADORA","SOLUCIONES","TRANSPORTES","IMPORTADORA","PROVEEDORA")[cluster_idx],
    sample(word_root, N_VENDORS, replace = TRUE),
    sample(word_theme, N_VENDORS, replace = TRUE),
    sample(legal_suf, N_VENDORS, replace = TRUE)
  ),
  RFC                      = rand_rfc(N_VENDORS),
  `Registro Impositivo`    = paste0(RFC, "."),
  `Fecha Creacion Prov`    = rand_date_str(creacion),
  `Actualizacion Provedor` = rand_date_str(actualiza),
  `Cabecera Actualizada Por` = paste(sample(100000:999999, N_VENDORS), "Usuario Demo"),
  `Fecha Proveedor Inactivo` = NA_character_,
  `Parent Vendor Id`       = NA,
  `Fuente Abasto Padre`    = NA,
  `Site Id Proveedor`      = sample(300000:900000, N_VENDORS),
  Site                     = site_info$site,
  FA                       = sample(c("Si", "No"), N_VENDORS, replace = TRUE, prob = c(0.85, 0.15)),
  `Fuente Abasto`          = NA,
  `Fecha Site Inactivo`    = NA_character_,
  `Actualizacion Site`     = rand_date_str(actualiza),
  `Sucrusales Actualizadas por` = paste(sample(1000000:9999999, N_VENDORS), "Perfil Prueba"),
  `Metodo de Pago`         = arche$metodo_pago,
  `Terminos Pago`          = paste(arche$terminos_dias, "dias"),
  `Grupo Pago`             = recode(arche$tipo_proveedor,
                                     COMERCIALIZADORES = "SERVICIOS-GENERALES",
                                     SERVICIOS = "SERVICIOS-GENERALES",
                                     TRANSPORTISTAS = "LOGISTICA-NACIONAL",
                                     IMPORTADORES = "PROVEEDORES-IMPORTACION",
                                     OUTLIER = "SIN-CLASIFICAR"),
  `Calculo Impuesto`       = sample(c("Y", "N"), N_VENDORS, replace = TRUE, prob = c(0.6, 0.4)),
  Impuesto                 = ifelse(arche$moneda == "USD", "TASA-0%IVA", "TASA-16%IVA"),
  `Impuesto Incluidos`     = sample(c("Y", "N"), N_VENDORS, replace = TRUE, prob = c(0.5, 0.5)),
  `Aplica Grupo Retencion` = sample(c("Y", "N"), N_VENDORS, replace = TRUE, prob = c(0.2, 0.8)),
  `Grupo Retencion`        = NA,
  Correo                   = NA,
  Direccion                = sprintf("AV %s %d INT %d COLONIA %s %s %s",
                                      sample(word_root, N_VENDORS, replace = TRUE),
                                      sample(100:9999, N_VENDORS, replace = TRUE),
                                      sample(1:50, N_VENDORS, replace = TRUE),
                                      sample(word_root, N_VENDORS, replace = TRUE),
                                      str_remove(site_info$site, "^[0-9]+"),
                                      site_info$estado),
  Pais                     = "MX",
  Telefono                 = NA,
  Banco                    = NA,
  `Prioridad Cuenta`       = NA,
  Cuenta                   = bank_account,
  `Inactivacion Cuenta`    = NA,
  `Actualizacion Cuenta`   = NA,
  `Referencia Bancaria`    = NA,
  `Referencia Adicional`   = NA,
  `Cuenta Pasivo`          = NA,
  `Cuenta Anticipo`        = NA,
  `Estatus Fe`             = "Validado",
  `Pago Independiente`     = NA,
  Resico                   = NA,
  `Sucursal Compra`        = "Y",
  `Sucursal Pago`          = "N"
) |>
  mutate(
    # Structured (not random) missingness, conditioned on vendor type
    Telefono = NA_character_,
    Banco    = NA_character_,
    Resico   = if_else(size_factor < quantile(size_factor, 0.35), "Y", "N")
  )

# keep latent factors around for payment simulation + later diagnostics
vendor_latent <- tibble(
  `Id Proveedor` = vendor_id,
  tipo_proveedor = arche$tipo_proveedor,
  site           = site_info$site,
  size_factor    = size_factor,
  risk_score     = risk_score,
  terminos_dias  = arche$terminos_dias,
  ciclo_dias     = arche$ciclo_dias,
  ciclo_jitter   = arche$ciclo_jitter,
  n_pagos_mean   = arche$n_pagos_mean,
  moneda         = arche$moneda,
  bank_account   = bank_account,
  nombre         = maestro$`Nombre Proveedor`
)

## ------------------------------------------------------------------
## 3. Simulate payments (Pagos) — periodic cadence per vendor (-> loops)
## ------------------------------------------------------------------
simulate_vendor_payments <- function(v) {
  n_pagos <- max(1, rpois(1, v$n_pagos_mean))

  if (is.na(v$ciclo_dias)) {
    # OUTLIER archetype: irregular Poisson-process timing, no periodicity
    fechas <- sort(DATE_RANGE[1] + sort(sample(0:as.numeric(diff(DATE_RANGE)), n_pagos)))
  } else {
    # Periodic cadence with jitter -> creates a loop under time-delay embedding
    start  <- DATE_RANGE[1] + sample(0:v$ciclo_dias, 1)
    fechas <- start + round((seq_len(n_pagos) - 1) * v$ciclo_dias +
                               rnorm(n_pagos, 0, v$ciclo_jitter))
    fechas <- fechas[fechas >= DATE_RANGE[1] & fechas <= DATE_RANGE[2]]
    if (length(fechas) == 0) fechas <- DATE_RANGE[1] + sample(1:30, 1)
  }

  day_of_year <- yday(fechas)
  seasonal    <- 1 + 0.15 * sin(2 * pi * day_of_year / 365 + v$size_factor %% (2 * pi))
  importe     <- v$size_factor * seasonal * rlnorm(length(fechas), 0, 0.25)

  tibble(
    FECHA_D_PAGO    = fechas,
    VENDOR_ID       = v$`Id Proveedor`,
    SITE            = v$site,
    VENDOR_NAME     = v$nombre,
    FECHA_FACTURA   = fechas - v$terminos_dias - sample(0:3, length(fechas), replace = TRUE),
    FECHA_VENCIMIENTO = fechas - sample(0:2, length(fechas), replace = TRUE),
    IMPORTE_AP      = round(importe, 2),
    moneda          = v$moneda,
    bank_account    = v$bank_account
  )
}

pagos_raw <- vendor_latent |>
  split(seq_len(nrow(vendor_latent))) |>
  map_dfr(simulate_vendor_payments)

n_pay <- nrow(pagos_raw)

pagos <- pagos_raw |>
  mutate(
    TIPO            = "CENTRO",
    INVOICE_ID      = sample(10000000:99999999, n_pay, replace = TRUE),
    SEGMENT4        = paste0(sample(10:99, n_pay, replace = TRUE), "MX", sample(1000:9999, n_pay, replace = TRUE)),
    SEGMENT1        = str_sub(bank_account, 1, 3) |> paste0(sample(100000:999999, n_pay, replace = TRUE), "A", sample(1:9, n_pay, replace = TRUE)),
    ATTRIBUTE1      = if_else(runif(n_pay) < 0.3, as.character(sample(1000000000:9999999999, n_pay, replace = TRUE)), NA_character_),
    REFERENCIA      = NA_character_,
    NUM_FACTURA     = if_else(
      runif(n_pay) < 0.5,
      sprintf("%dABC%d/%sMTY%02d", sample(1:9, n_pay, replace = TRUE), sample(100:999, n_pay, replace = TRUE),
              SITE, sample(20:25, n_pay, replace = TRUE)),
      replicate(n_pay, paste0(
        paste0(sample(c(LETTERS, 0:9), 8), collapse = ""), "-",
        paste0(sample(c(LETTERS, 0:9), 4), collapse = ""), "-",
        paste0(sample(c(LETTERS, 0:9), 4), collapse = ""), "-",
        paste0(sample(c(LETTERS, 0:9), 4), collapse = ""), "-",
        paste0(sample(c(LETTERS, 0:9), 12), collapse = "")
      ))
    ),
    PAGADO          = sprintf(" $%s ", formatC(IMPORTE_AP, format = "f", digits = 2, big.mark = ",")),
    PAGO_MX         = if_else(moneda == "USD", sprintf(" $%s ", formatC(IMPORTE_AP * 18.5, format = "f", digits = 2, big.mark = ",")), NA_character_),
    TIPO_CAMBIO     = if_else(moneda == "USD", round(runif(n_pay, 17, 19), 4), NA_real_),
    TOTAL_TAX_AMOUNT = round(if_else(moneda == "USD", 0, IMPORTE_AP * 0.16 / 1.16), 2),
    DESCRIPTION     = paste(sample(10000000:99999999, n_pay, replace = TRUE), "Almacen", SITE, sample(1000000:9999999, n_pay, replace = TRUE), paste0("CD_", SITE, "_", sample(1000:9999, n_pay, replace = TRUE))),
    PAYMENT_REASON_COMMENTS = if_else(runif(n_pay) < 0.15, paste0("DEMO", sample(1000000:9999999, n_pay, replace = TRUE), "REAUT", sample(100:999, n_pay, replace = TRUE)), NA_character_),
    TIPO_1          = NA_character_,
    GPO_PAGO        = sample(c("VENDOR-TR", "PS-TR"), n_pay, replace = TRUE),
    PLZ             = sample(c(12, 30, 45, 60), n_pay, replace = TRUE),
    NO_DOC          = sample(3000000000:3000999999, n_pay, replace = TRUE),
    IMPORTE_DOC     = round(IMPORTE_AP * runif(n_pay, 1, 12), 2),
    BANK_ACCOUNT_NUM = bank_account,
    BANK_ACCOUNT_NAME = paste(SITE, "EGRESOS PAGOS CEDIS"),
    CHECK_ID        = sample(30000000:30999999, n_pay, replace = TRUE),
    BANK_NUM        = sprintf("%04d", sample(1:99, n_pay, replace = TRUE)),
    INVOICE_ID_1    = INVOICE_ID,
    APPROVAL_DESCRIPTION = NA_character_,
    SOURCE          = "SIMULADO",
    UUID            = replicate(n_pay, paste0(
      paste0(sample(c(LETTERS, 0:9), 8), collapse = ""), "-",
      paste0(sample(c(LETTERS, 0:9), 4), collapse = ""), "-",
      paste0(sample(c(LETTERS, 0:9), 4), collapse = ""), "-",
      paste0(sample(c(LETTERS, 0:9), 4), collapse = ""), "-",
      paste0(sample(c(LETTERS, 0:9), 12), collapse = "")
    ))
  )

## ------------------------------------------------------------------
## 4. Inject sporadic anomalous payments (outliers) into normal vendors
## ------------------------------------------------------------------
OUTLIER_PAYMENT_FRAC <- 0.015
n_outlier <- round(n_pay * OUTLIER_PAYMENT_FRAC)
outlier_rows <- sample(n_pay, n_outlier)

pagos$IMPORTE_AP[outlier_rows] <- pagos$IMPORTE_AP[outlier_rows] * runif(n_outlier, 6, 25)
pagos$PAGADO[outlier_rows] <- sprintf(" $%s ", formatC(pagos$IMPORTE_AP[outlier_rows], format = "f", digits = 2, big.mark = ","))
# roughly half of injected anomalies also get an impossible date ordering
flip <- outlier_rows[runif(n_outlier) < 0.5]
pagos$FECHA_VENCIMIENTO[flip] <- pagos$FECHA_FACTURA[flip] - sample(5:30, length(flip), replace = TRUE)

## ------------------------------------------------------------------
## 5. Format & select final columns (match source schema exactly)
## ------------------------------------------------------------------
maestro_final <- maestro |>
  select(`Unidad Operativa`, `Id Proveedor`, `Tipo Proveedor`, `Nombre Proveedor`, RFC,
         `Registro Impositivo`, `Fecha Creacion Prov`, `Actualizacion Provedor`,
         `Cabecera Actualizada Por`, `Fecha Proveedor Inactivo`, `Parent Vendor Id`,
         `Fuente Abasto Padre`, `Site Id Proveedor`, Site, FA, `Fuente Abasto`,
         `Fecha Site Inactivo`, `Actualizacion Site`, `Sucrusales Actualizadas por`,
         `Metodo de Pago`, `Terminos Pago`, `Grupo Pago`, `Calculo Impuesto`, Impuesto,
         `Impuesto Incluidos`, `Aplica Grupo Retencion`, `Grupo Retencion`, Correo,
         Direccion, Pais, Telefono, Banco, `Prioridad Cuenta`, Cuenta,
         `Inactivacion Cuenta`, `Actualizacion Cuenta`, `Referencia Bancaria`,
         `Referencia Adicional`, `Cuenta Pasivo`, `Cuenta Anticipo`, `Estatus Fe`,
         `Pago Independiente`, Resico, `Sucursal Compra`, `Sucursal Pago`)

pagos_final <- pagos |>
  mutate(
    FECHA_D_PAGO      = format(FECHA_D_PAGO, "%d/%m/%y"),
    FECHA_FACTURA     = format(FECHA_FACTURA, "%d/%m/%y"),
    FECHA_VENCIMIENTO = format(FECHA_VENCIMIENTO, "%d/%m/%y")
  ) |>
  select(TIPO, FECHA_D_PAGO, VENDOR_ID, INVOICE_ID, SITE, SEGMENT4, VENDOR_NAME, SEGMENT1,
         ATTRIBUTE1, REFERENCIA, FECHA_FACTURA, FECHA_VENCIMIENTO, NUM_FACTURA, IMPORTE_AP,
         PAGADO, PAGO_MX, TIPO_CAMBIO, TOTAL_TAX_AMOUNT, DESCRIPTION, PAYMENT_REASON_COMMENTS,
         TIPO_1, GPO_PAGO, PLZ, NO_DOC, IMPORTE_DOC, BANK_ACCOUNT_NUM, BANK_ACCOUNT_NAME,
         CHECK_ID, BANK_NUM, INVOICE_ID_1, APPROVAL_DESCRIPTION, SOURCE, UUID)

## ------------------------------------------------------------------
## 6. Write outputs
## ------------------------------------------------------------------
write.csv(maestro_final, file.path(OUT_DIR, "Maestro_simulado.csv"), row.names = FALSE, na = "")
write.csv(pagos_final,   file.path(OUT_DIR, "Pagos_simulado.csv"),   row.names = FALSE, na = "")

# Side table kept only for diagnostics / downstream TDA work (ground-truth
# archetype labels won't exist in a real export, so keep it separate).
write.csv(vendor_latent |> select(`Id Proveedor`, tipo_proveedor, site, size_factor, risk_score),
          file.path(OUT_DIR, "Maestro_ground_truth_clusters.csv"), row.names = FALSE)

message(sprintf("Vendors: %d | Payments: %d | Outlier payments injected: %d",
                 nrow(maestro_final), nrow(pagos_final), n_outlier))
