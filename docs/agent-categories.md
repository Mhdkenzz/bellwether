# Agent description categories

**Use these 10 groups when making agents.** Every person in a population must have every category filled in.
The list lives in code at `bellwether/population/categories.py` (the single source of truth); `tests/test_categories.py`
fails if any sampled agent is missing a category. Anything new about a person belongs in one of these groups, or in a
new group added to that file.

How to write agents by hand or extend the pools: [guide.md](../guide.md).

Option pools are in `bellwether/population/pools.py`. Where marked *trait-matched*, the option is picked to fit the
person's traits; minors and adults draw from age-appropriate options; relationship status agrees with living situation.

## 1. Identity

| Category | Field | Options |
| --- | --- | --- |
| First name | `name` | 240 names |
| Age | `age` | range from config |
| Life stage | `life_stage` | 6 |
| Occupation | `occupation` | 68 (+ cohort titles) |
| Location | `location` | 5 |

## 2. Money

| Category | Field | Options |
| --- | --- | --- |
| Income band | `income` | 3 bands |
| Spending money | `budget` | range per band |

## 3. Personality

| Category | Field | Options |
| --- | --- | --- |
| Decision traits | `traits` | 4 scores × 5 wording levels |
| Big Five | `big_five` | 5 scores |
| Introvert / ambivert / extrovert | `personality_type` | 3 |
| Temperament | `temperament` | 10 phrases, 2 each |
| Chronotype | `chronotype` | 3 |
| How easily swayed | `susceptibility` | score |

## 4. Habits and tastes

| Category | Field | Options |
| --- | --- | --- |
| Interests | `interests` | 59, 3 each |
| Values | `values` | 20, 2 each |
| Shopping style | `shopping_style` | 12 |
| Media habit | `media_habit` | 12 |
| Decision style | `decision_style` | 10 |
| Quirk | `quirk` | 48 |
| Music | `music` | 15 |
| Favourite food | `food` | 12 |

## 5. Life situation

| Category | Field | Options |
| --- | --- | --- |
| Living situation | `living` | 32 |
| Short-term goal | `goal_short` | 19 |
| Long-term dream | `goal_long` | 11 |
| Worries | `worries` | 13, 2 each |
| What's going on right now | `life_context` | 10 |

## 6. Social life

| Category | Field | Options |
| --- | --- | --- |
| Social platforms | `platforms` | 3 (0-3 each) |
| Posting frequency | `posting` | 4 |

## 7. Health and wellbeing

| Category | Field | Options |
| --- | --- | --- |
| Health | `health` | 10 |
| Sleep | `sleep` | 6 |
| Fitness | `fitness` | 4 |

## 8. Relationships and home

| Category | Field | Options |
| --- | --- | --- |
| Relationship status | `relationship` | 5 under 18 / 5+ adults |
| Pets | `pets` | 8 |
| Family closeness | `family_closeness` | 5 |

## 9. Background

| Category | Field | Options |
| --- | --- | --- |
| Where they grew up | `hometown` | 5 |
| Money growing up | `family_money` | 4 |
| Formative experience | `formative` | 12 |

## 10. Attitudes and beliefs

| Category | Field | Options |
| --- | --- | --- |
| Money mindset | `money_mindset` | 5 |
| Attitude to brands | `brand_attitude` | 5 |
| Attitude to tech | `tech_attitude` | 3 |
| Cause they care about | `cause` | 9 |
