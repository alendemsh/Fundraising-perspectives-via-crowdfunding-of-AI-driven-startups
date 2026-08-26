## Libraries ===================================================================
library(tidyverse)
library(readxl)
library(fixest)
library(modelsummary)
library(marginaleffects)
library(plm)
library(pandoc) 
library(ggplot2) 
library(reshape2)
library(car)
library(patchwork)
library(dplyr)
library(lubridate)
library(quantreg)
set.seed(123)

## Formatting ==================================================================
options(scipen = 999)
theme_set(theme_bw(base_size = 12, base_family = "Times"))

## Data load ===================================================================

data <- read_csv('final_data.csv')
glimpse(data)

## OLS regressions =============================================================
### Model 1: controls only -----------------------------------------------------
m1_ols <- feols(
  log_funding_ratio ~ duration_days + title_length_chars + has_video 
    + log_story_image_count + creator_competence_count + gii,
  data = data,
  vcov = "hetero"
)
vif_m1 <- vif(lm(
  log_funding_ratio ~ duration_days + title_length_chars + has_video 
  + log_story_image_count + creator_competence_count + gii,
  data = data
))

### Model 2: all main effects -------------------------------------------------
m2_ols <- feols(
  log_funding_ratio ~ duration_days + title_length_chars + has_video 
  + log_story_image_count + creator_competence_count 
  + story_external_links_count +
    has_faq_section +
    log_ai_keyword_count + gii +
    creator_created_projects,
  data = data,
  vcov = "hetero"
)

vif_m2 <- vif(lm(
  log_funding_ratio ~ duration_days + title_length_chars + has_video 
  + log_story_image_count + creator_competence_count 
  + story_external_links_count +
    has_faq_section +
    log_ai_keyword_count + gii +
    creator_created_projects,
  data = data
))

### Model 3: full model with interaction (H4) ----------------------------------
data <- data %>%
  mutate(
    gii_c = gii - mean(gii, na.rm = TRUE),
    log_ai_keyword_count_c = log_ai_keyword_count - mean(log_ai_keyword_count, na.rm = TRUE)
  )

m3_ols <- feols(
  log_funding_ratio ~ duration_days + title_length_chars + has_video 
  + log_story_image_count + creator_competence_count 
  + story_external_links_count +
    has_faq_section +
    log_ai_keyword_count_c*gii_c +
    creator_created_projects,
  data = data,
  vcov = "hetero"
)

vif_m3 <- vif(lm(
  log_funding_ratio ~ duration_days + title_length_chars + has_video 
  + log_story_image_count + creator_competence_count 
  + story_external_links_count +
    has_faq_section +
    log_ai_keyword_count_c*gii_c +
    creator_created_projects,
  data = data
))

## Logit regressions ===========================================================
### Logit 1: controls only -----------------------------------------------------
m1_logit <- feglm(
  state_success ~ duration_days + title_length_chars + has_video 
  + log_story_image_count + creator_competence_count + gii,
  data = data,
  family = binomial("logit"),
  vcov = "hetero"
)

### Logit 2: full model without interaction ------------------------------------
m2_logit <- feglm(
  state_success ~ duration_days + title_length_chars + has_video 
  + log_story_image_count + creator_competence_count 
  + story_external_links_count +
    has_faq_section +
    log_ai_keyword_count + gii +
    creator_created_projects,
  data = data,
  family = binomial("logit"),
  vcov = "hetero"
)

### Logit 3: full model with interaction ---------------------------------------
m3_logit <- feglm(
  state_success ~ duration_days + title_length_chars + has_video 
  + log_story_image_count + creator_competence_count 
  + story_external_links_count +
    has_faq_section +
    log_ai_keyword_count_c*gii_c +
    creator_created_projects,
  data = data,
  family = binomial("logit"),
  vcov = "hetero"
)

## Tables ======================================================================

modelsummary(
  list(
    "OLS: Controls" = m1_ols,
    "OLS: Full" = m2_ols,
    "OLS: Full + Interaction" = m3_ols
  ),
  stars = TRUE,
  statistic = "({std.error})",
  gof_omit = "IC|Log|Adj|Pseudo" 
  #,
  #output = "ols_regression_results.docx"
  )

modelsummary(
  list(
    "Logit: Controls" = m1_logit,
    "Logit: Full" = m2_logit,
    "Logit: Full + Interaction" = m3_logit
  ),
  stars = TRUE,
  statistic = "({std.error})",
  gof_omit = "IC|Log|Adj"
  #,
  #output = "logit_regression_results.docx"
  )

## OLS regressions without USA =================================================
### Model: full model without interaction ------------------------------------
data_no_us <- data[data$created_location_country != "United States", ]

noUSA_1_ols <- feols(
  log_funding_ratio ~ duration_days + title_length_chars + has_video 
  + log_story_image_count + creator_competence_count 
  + story_external_links_count +
    has_faq_section +
    log_ai_keyword_count + gii +
    creator_created_projects +
    duration_days + title_length_chars,
  data = data_no_us,
  vcov = "hetero"
)

vif(lm(
  log_funding_ratio ~ duration_days + title_length_chars + has_video 
  + log_story_image_count + creator_competence_count 
  + story_external_links_count +
    has_faq_section +
    log_ai_keyword_count + gii +
    creator_created_projects +
    duration_days + title_length_chars,
  data = data_no_us
))

### Model: full model with interaction (H4) ----------------------------------
noUSA_2_ols <- feols(
  log_funding_ratio ~ duration_days + title_length_chars + has_video 
  + log_story_image_count + creator_competence_count 
  + story_external_links_count +
    has_faq_section +
    log_ai_keyword_count_c*gii_c +
    creator_created_projects +
    duration_days + title_length_chars,
  data = data_no_us,
  vcov = "hetero"
)

vif(lm(
  log_funding_ratio ~ duration_days + title_length_chars + has_video 
  + log_story_image_count + creator_competence_count 
  + story_external_links_count +
    has_faq_section +
    log_ai_keyword_count_c*gii_c +
    creator_created_projects +
    duration_days + title_length_chars,
  data = data_no_us
))

modelsummary(
  list(
    "OLS without USA: Full" = noUSA_1_ols,
    "OLS without USA: Full + Interaction" = noUSA_2_ols
  ),
  stars = TRUE,
  statistic = "({std.error})",
  gof_omit = "IC|Log|Adj|Pseudo" 
  #,
  #output = "ols_withoutUSA_regression_results.docx"
)

## Graphs ======================================================================
### Two-way Interractions graph in Excel ---------------------------------------
b <- coef(m3_ols)

b["log_ai_keyword_count_c"]        
b["gii_c"]                         
b["log_ai_keyword_count_c:gii_c"] 
b["(Intercept)"]                   

mean(data$log_ai_keyword_count_c, na.rm = TRUE)  
sd(data$log_ai_keyword_count_c, na.rm = TRUE)    

mean(data$gii_c, na.rm = TRUE)                   
sd(data$gii_c, na.rm = TRUE)                     

V <- vcov(m3_ols, vcov = "hetero")
#  variance of coefficient of IV
V["log_ai_keyword_count_c",
  "log_ai_keyword_count_c"]

#  variance of interaction coefficient
V["log_ai_keyword_count_c:gii_c",
  "log_ai_keyword_count_c:gii_c"]

#  covariance IV coefficient and interaction
V["log_ai_keyword_count_c",
  "log_ai_keyword_count_c:gii_c"]

nobs(m3_ols)

### interaction plot (AI × GII) ------------------------------------------------
p <- plot_predictions(
  m3_ols,
  condition = c("log_ai_keyword_count_c", "gii_c")
)

p +
  labs(
    x = "AI keywords (log, centered)",
    y = "Predicted log funding ratio",
    color = "Deviation from mean GII"
  ) +
  guides(fill = "none")


### Predicted vs Actual --------------------------------------------------------
par(mfrow = c(1,1))
data$pred <- predict(m3_ols)

par(family = "Times", ps = 12)

plot(
  data$pred,
  data$log_funding_ratio,
  xlab = "Predicted",
  ylab = "Actual",
)

abline(0, 1)

## VIF =========================================================================
vif_table <- bind_rows(
  enframe(vif_m1, name = "Variable", value = "VIF") %>%
    mutate(Model = "Model 1"),
  
  enframe(vif_m2, name = "Variable", value = "VIF") %>%
    mutate(Model = "Model 2"),
  
  enframe(vif_m3, name = "Variable", value = "VIF") %>%
    mutate(Model = "Model 3"),
)

# CSV
write.csv(vif_table,
          "vif_table.csv",
          row.names = FALSE)

## 2021-2022 vs 2023-2026  =====================================================
data <- data %>%
  mutate(
    launched_at = ymd_hms(launched_at),
    year = year(launched_at)
  )

df_2021_2023 <- data %>%
  filter(year >= 2021 & year <= 2023)

df_2024_2026 <- data %>%
  filter(year >= 2024 & year <= 2026)

### 2021-2023 ------------------------------------------------------------------
m3_ols_23 <- feols(
  log_funding_ratio ~ duration_days + title_length_chars + has_video 
  + log_story_image_count + creator_competence_count 
  + story_external_links_count +
    has_faq_section +
    log_ai_keyword_count_c*gii_c +
    creator_created_projects,
  data = df_2021_2023,
  vcov = "hetero"
)

### 2024-2026 ------------------------------------------------------------------
m3_ols_26 <- feols(
  log_funding_ratio ~ duration_days + title_length_chars + has_video 
  + log_story_image_count + creator_competence_count 
  + story_external_links_count +
    has_faq_section +
    log_ai_keyword_count_c*gii_c +
    creator_created_projects,
  data = df_2024_2026,
  vcov = "hetero"
)

### comparison -----------------------------------------------------------------

modelsummary(
  list(
    "OLS with interraction: 2021 - 2023" = m3_ols_23,
    "OLS with interraction: 2024 - 2026" = m3_ols_26
  ),
  stars = TRUE,
  statistic = "({std.error})",
  gof_omit = "IC|Log|Adj|Pseudo" 
  #,
  #output = "ols_regression_years.docx"
)

### Quantile regression ========================================================
model_quantiles <- rq(
  log_funding_ratio ~ duration_days + title_length_chars + has_video 
  + log_story_image_count + creator_competence_count 
  + story_external_links_count +
    has_faq_section +
    log_ai_keyword_count_c*gii_c +
    creator_created_projects,
  tau = c(0.10, 0.25, 0.50, 0.75, 0.90),
  data = data
)

# 0.10 - Проекты с очень низким условным log_funding_ratio
# 0.25 - Нижняя часть распределения  
# 0.50 - Медианный уровень                                   
# 0.75 - Верхняя часть распределения                        
# 0.90 - Проекты с очень высоким log_funding_ratio

quantile_results <- summary(
  model_quantiles,
  se = "boot",
  R = 1000
)

quantile_results
plot(quantile_results)

### Проверка различия коэф-тов в 50 и 75 квантилях (H0: коэф-ты одинаковые) ----
model_q50 <- rq(
  log_funding_ratio ~ duration_days + title_length_chars + has_video 
  + log_story_image_count + creator_competence_count 
  + story_external_links_count +
    has_faq_section +
    log_ai_keyword_count_c*gii_c +
    creator_created_projects,
  tau = 0.5,
  data = data
)

model_q75 <- rq(
  log_funding_ratio ~ duration_days + title_length_chars + has_video 
  + log_story_image_count + creator_competence_count 
  + story_external_links_count +
    has_faq_section +
    log_ai_keyword_count_c*gii_c +
    creator_created_projects,
  tau = 0.75,
  data = data
)

anova(model_q50, model_q75, joint = FALSE)
# p-value > 0.05, коэффициент взаимодействия статистически не различается между медианой и 75-м квантилем.

### Вывод в таблицы ------------------------------------------------------------
model_q10 <- update(model_quantiles, tau = 0.10)
model_q25 <- update(model_quantiles, tau = 0.25)
model_q50 <- update(model_quantiles, tau = 0.50)
model_q75 <- update(model_quantiles, tau = 0.75)
model_q90 <- update(model_quantiles, tau = 0.90)

modelsummary(
  list(
    "10th percentile" =  model_q10,
    "25th percentile" = model_q25,
    "Median" =  model_q50,
    "75th percentile" = model_q75,
    "90th percentile" = model_q90
  ),
  stars = TRUE,
  statistic = "({std.error})",
  gof_map = "nobs",
  title = "Quantile Regression Results",
  notes = "Bootstrap standard errors based on 1,000 replications are reported in parentheses."
  #,
  #output = "Quantile_Regression_Results.docx"
)
