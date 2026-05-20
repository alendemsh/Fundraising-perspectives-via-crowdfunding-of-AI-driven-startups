## Libraries ===================================================================
library(tidyverse)
library(readxl)
library(fixest)
library(modelsummary)
library(marginaleffects)
library(plm)
library(pandoc) #для конвертации табличек в отдельные файлы
library(ggplot2) #для графиков
library(reshape2)
library(car)
library(patchwork)

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
#interaction plot (AI × GII)
p <- plot_predictions(
  m3_ols,
  condition = c("log_ai_keyword_count_c", "gii_c")
)

p +
  labs(
    x = "AI keywords (log, centered)",
    y = "Predicted funding success",
    color = "Deviation from mean GII"
  ) +
  guides(fill = "none")

#Predicted vs Actual
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

#VIF
vif_table <- bind_rows(
  enframe(vif_m1, name = "Variable", value = "VIF") %>%
    mutate(Model = "Model 1"),
  
  enframe(vif_m2, name = "Variable", value = "VIF") %>%
    mutate(Model = "Model 2"),
  
  enframe(vif_m3, name = "Variable", value = "VIF") %>%
    mutate(Model = "Model 3"),
)

# Сохраняем CSV
write.csv(vif_table,
          "vif_table.csv",
          row.names = FALSE)
