# Fundraising Perspectives via Crowdfunding of AI-Driven Startups

[Русская версия](README_RU.md)

## Overview

This repository contains the data-collection and empirical-analysis workflow for a research project examining the factors associated with the crowdfunding performance of AI-driven startups. The study focuses on reward-based Kickstarter campaigns and evaluates whether campaign communication, founder credibility, AI-related signaling, and home-country technological legitimacy are associated with fundraising outcomes.

The project combines automated web scraping in Python, exploratory data analysis, and econometric modeling in R. The final analytical sample contains **756 AI-related Technology campaigns completed between January 2021 and March 2026**.

## Research question

**How are campaign presentation characteristics, founder credibility, AI-related signaling, and country-level technological legitimacy associated with the fundraising success of AI-driven startups?**

The analysis is grounded in signaling theory and social presence theory. Under conditions of information asymmetry, potential backers cannot directly evaluate the technical quality of an AI product and may therefore rely on observable signals presented on the campaign page.

## Research workflow

1. **Data collection:** Kickstarter campaign data were collected from publicly available pages using an automated Python parser.
2. **Data preparation:** observations were cleaned, transformed, and combined with annual Global Innovation Index data.
3. **Exploratory analysis:** the distributions of campaigns, variables, countries, Technology subcategories, and crowdfunding outcomes were examined in Python.
4. **Econometric analysis:** OLS models were estimated as the main specification in R.
5. **Interaction analysis:** the moderating role of the Global Innovation Index in the relationship between AI-related signaling and crowdfunding performance was evaluated.
6. **Robustness check:** logistic regression was estimated using campaign success as an alternative binary outcome.
7. **Additional analysis:** quantile regressions were used to examine whether the estimated relationships differ across the conditional distribution of crowdfunding performance.

## Data collection and sample

Campaign-level information was collected with **Python 3.14**, using **BeautifulSoup** and **Playwright**. Campaigns were selected according to the following criteria:

- the campaign title contained the term `AI`;
- the campaign belonged to Kickstarter's Technology category;
- the campaign had a final status of either successful or failed;
- the campaign was reward-based;
- the campaign ended between January 2021 and March 2026.

The initial sample contained 1,000 campaigns: 500 successful and 500 failed projects. After removing observations with missing values and restricting the period to match the availability of Global Innovation Index data, the final sample contained **756 campaigns from 38 countries and 15 Technology subcategories**.

> The balanced sampling design was selected to ensure sufficient variation in campaign outcomes. Consequently, model estimates should be interpreted as associations within the constructed analytical sample rather than as population-level estimates of Kickstarter success probabilities.

## Main variables

### Outcomes

- **Funding ratio:** pledged amount divided by the campaign goal.
- **Log funding ratio:** `log(1 + funding ratio)`, used as the dependent variable in the OLS and quantile regressions.
- **Campaign success:** binary indicator equal to 1 when a campaign reached its funding goal and 0 otherwise, used in the logistic robustness models.

### Explanatory variables

- number of external links in the campaign story;
- presence of a FAQ section;
- AI-related keyword count in the campaign description;
- founder's prior Kickstarter fundraising experience;
- Global Innovation Index of the campaign's home country.

### Control variables

- campaign duration;
- title length;
- presence of video;
- number of images;
- creator competence keyword count.

Skewed count variables were transformed using `log(x + 1)`. AI-related keyword count and the Global Innovation Index were mean-centered before constructing the interaction term.

## Methods

The main analysis was conducted in **R 4.4.3**. OLS models were estimated using `fixest`, with heteroskedasticity-robust standard errors. Regression tables were produced with `modelsummary`.

Three main specifications were estimated:

1. a control-variable model;
2. a full model including the main explanatory variables;
3. a full model including the interaction between AI-related signaling and the Global Innovation Index.

Variance Inflation Factors were examined for all OLS specifications; all values remained below 5. Logistic regression was used as a robustness check with campaign success as the dependent variable. Quantile regression provides an additional assessment of heterogeneity across different levels of crowdfunding performance.

## Key findings

- **External links:** the number of external links is positively and statistically significantly associated with crowdfunding performance. In the full OLS model, one additional external link is associated with an approximately **8.44% higher expected value of funding ratio plus one**, holding other factors constant.
- **FAQ section:** campaigns containing a FAQ section have an expected value of funding ratio plus one approximately **176.21% higher** than campaigns without a FAQ section, holding other factors constant.
- **Founder experience:** prior Kickstarter fundraising experience is positively associated with campaign performance. In the full OLS model, campaigns launched by experienced founders have an expected value of funding ratio plus one approximately **120.34% higher** than campaigns without such experience.
- **AI-related signaling:** the frequency of AI-related terminology is not statistically significant in either the main OLS model or the logistic robustness model. The results therefore do not support a positive association between repeated AI terminology and crowdfunding performance.
- **Interaction effect:** the interaction between AI-related signaling and the Global Innovation Index is negative and statistically significant in the OLS specification. This suggests that the association between AI-related signaling and crowdfunding performance becomes weaker as home-country technological legitimacy increases. However, the interaction is statistically insignificant in the logistic robustness model, so the moderation result is **not robust across model specifications**.

Overall, the findings suggest that transparency, campaign communication, and founder credibility are more consistently associated with crowdfunding outcomes than the repeated use of AI-related terminology.

## Repository contents

- **Python parser:** automated collection of publicly available Kickstarter campaign information.
- **Python EDA:** data cleaning, descriptive statistics, distribution analysis, and exploratory visualizations.
- **R analysis:** variable transformations, descriptive analysis, OLS estimation, interaction analysis, logistic robustness models, quantile regression, and publication-ready tables and figures.
- **Research paper:** full description of the theoretical framework, hypotheses, methodology, results, discussion, and limitations.

## Reproducibility

The workflow requires:

- Python 3.14;
- BeautifulSoup;
- Playwright;
- R 4.4.3;
- `fixest`;
- `modelsummary`;
- the R packages loaded in the analysis scripts.

The parser collects data from live web pages, so its output may change if Kickstarter modifies its page structure or if campaign pages are updated or removed. Users should review Kickstarter's current terms and applicable data-collection requirements before running the parser. File paths may also need to be adjusted to the local project directory.

## Limitations

- AI-driven projects were identified through the presence of `AI` in campaign titles, which may omit relevant campaigns or include projects using the term superficially.
- The balanced sampling strategy does not reproduce the population success rate on Kickstarter.
- The sample is limited to reward-based campaigns in the Technology category and is geographically concentrated in the United States.
- Dictionary-based measures of AI terminology and creator competence may introduce classification error.
- The external-link measure may include repeated or platform-generated links.
- The observational research design does not support causal interpretation, and omitted-variable bias may remain.

## Author

**Alena Demysheva**  
International Programme in Business and Economics, Data-Driven Company track  
HSE University, St. Petersburg
