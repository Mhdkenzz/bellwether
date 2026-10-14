# Guide: making agents

An agent is one person in a Bellwether population. This guide covers how to write people who behave like
real, distinct humans and who fill all **10 description groups** (the list lives in
`bellwether/population/categories.py`).

**Every agent lives in a file.** Each community is a YAML file in `configs/populations/` with its people
written out under `agents:`, so you can read, edit and version every person, friendship and family link.

| Community | People | What it is |
| --- | --- | --- |
| `school-circle` | 25 | Juniors, seniors, outside friends and family around one school (the hoodie scenario's school) |
| `northgate-handwritten` | 27 | Students, outside friends, family and staff around Northgate High |
| `general-panel` | 38 | Mixed adults of all ages and walks of life |
| `all` | 90 | Everyone above, run together as one society |

`docs/all-agents.md` lists all of them in one readable file (rebuild it with `python -m bellwether roster`).

There are two ways to add people:

| | Write them yourself | Generate, then write out |
| --- | --- | --- |
| How | Add a person under `agents:` by hand | The generator draws people from option pools; `python -m bellwether export <name>` writes them into the file |
| Good for | Specific people you have in mind | Lots of variety quickly; then read and fix each one by hand |
| Code | `bellwether/population/handmade.py` | `sampler.py`, `depth.py`, `pools.py`, `export.py` |

Either way, what runs is what's written in the file.

---

## Quick start

1. Add a person to a community file (copy one from `configs/populations/northgate-handwritten.yaml`), or copy
   that whole file to start a new community.
2. Check it:

   ```bash
   .venv/bin/python -m bellwether population <name>
   ```

   This builds the population and prints each person, or stops with a clear message naming the person and the problem.
3. Rebuild the roster and run the tests:

   ```bash
   .venv/bin/python -m bellwether roster
   ```

   ```bash
   .venv/bin/python -m pytest -q
   ```

4. Run it, first with the fake backend (instant):

   ```bash
   .venv/bin/python -m bellwether run hoodie-life --population <name> --backend fake
   ```

## Choosing who runs: how many, and in what proportion

Every run asks two questions, in the terminal and in the dashboard's **New run** form:

1. **How many people?** Press Enter for everyone.
2. **In what proportion?** For `all`, this is the mix of communities; for one community, it's the mix of cohorts (for example
   juniors : seniors : friends : family). Press Enter for the natural mix.

**The most accurate result is everyone, in their natural mix.** That's the biggest sample, with nobody over- or
under-represented. A smaller run keeps the same proportions. A custom mix (`school-circle=50,general-panel=50` or `25:27:38`)
is allowed, but it can never ask for more people than are written; if it does, you're told the most it can run.
Without a terminal (or with `--yes`), runs use `--size` / `--mix`, or everyone.

Scenarios can target people by `cohort:` and, when communities run together, by `community:`.

---

## The population header

```yaml
population:
  name: northgate-handwritten        # unique; used on the command line and in run folders
  description: One line about who these people are.
  size: 27                           # informational; runs use everyone written unless told otherwise
  seed: 11                           # only matters if nobody lists `knows:` (then acquaintances are random)
  cohorts:                           # the sub-groups scenarios can target (select: {cohort: [...]})
    - {name: junior, label: junior at Northgate High, share: 0.4}
    - {name: family, label: parent or relative of a student, share: 0.2}
  groups:
    weak_ties_per_agent: 2           # random acquaintances, only used when nobody lists `knows:`
    cross_cohort_labels:             # how a tie between two cohorts is described
      junior|senior: schoolmate
      family|junior: family friend   # NOT "family" - real family comes from `family:` links
  min_trait_distance: 0.12           # no two people may have near-identical decision traits
  budget_label: to spend on wants this month
  agents:
    - name: ...
```

- **Shares** must add up to 1. When people are written out, shares only matter for generating new people: the `cohort` on
  each person is what counts.
- **Cohort names** must match what your scenarios select. `scenarios/hoodie-life.yaml` targets `junior`, `senior` and `friend`.
- **Platforms** a person can use are `instagram`, `tiktok` and `group_chat`, unless the config adds a `social_media:` block.

---

## The 10 groups, field by field

Write every field. Missing fields, misspelled fields and unknown fields all fail loudly. Write in the
**third person, without the name**, and use "their" rather than "his" or "her". Each phrase is dropped
into a sentence, so the "Shown as" column tells you what shape it needs.

### 1. Identity

| Field | Shown as | What to write |
| --- | --- | --- |
| `name` | — | First name, unique in the population. |
| `age` | — | 10–100. |
| `cohort` | — | One of the config's cohort names (optional, but scenarios use it). |
| `life_stage` | — | Exactly one of `student`, `early career`, `settling down`, `mid career`, `late career`, `retired`. **Under-18s must be `student`.** This decides which daily activities and obligations they get, for example class in the morning. |
| `occupation` | "Name, 16, *high school junior*" | Concrete: "apprentice electrician", not "works". |
| `location` | "…, *inner suburb*" | Area type: city centre, inner suburb, outer suburb, small town, rural area. |

### 2. Money

| Field | What to write |
| --- | --- |
| `income` | `low`, `mid` or `high`, meaning the household's or person's band. |
| `budget` | Money they can actually spend on wants in the run's time frame, in the config's currency. This is a **hard limit**: the engine blocks anything that costs more. Be realistic. A 15-year-old on $30 cannot buy a $60 hoodie, and that is the point. |

### 3. Personality

| Field | What to write |
| --- | --- |
| `traits` | The 4 decision traits, each 0–1. These move decisions directly; see the trait table below. |
| `big_five` | `openness`, `conscientiousness`, `extraversion`, `agreeableness`, `neuroticism`, each 0–1, all five required. |
| `chronotype` | Exactly `early bird`, `night owl` or `in between`. Affects energy and late-night activity. |
| `temperament` | Optional. If you leave it out, it is derived from the Big Five, which is usually best. |

**Decision traits (0 = very low, 1 = very high; 0.66 or more puts them in a segment):**

| Trait | High means | What it does in the engine |
| --- | --- | --- |
| `risk_tolerance` | Acts now, doesn't wait for proof | Pushes toward acting and away from "wait" |
| `price_sensitivity` | Price hurts | Penalises options that eat a big share of the budget; makes discounts pull harder |
| `trend_following` | Goes with what others do | Takes in more signals, follows hype and owners, scrolls feeds more |
| `social_influence` | Sways other people | Their words and posts travel further and land harder |

**Big Five → derived behaviour:** extraversion decides introvert (< 0.36), ambivert or extrovert (> 0.64).
Agreeableness and neuroticism, together with trend_following, set **how easily swayed** they are.
Neuroticism and extraversion set their baseline mood and stress.

**Make the numbers match the words.** A person who "researches everything before deciding" should
not have risk_tolerance 0.9. A person who "buys on impulse" should not have conscientiousness 0.9.
Spread people across the range: a real circle has a few 0.2s and a few 0.85s, not twenty 0.5s.

### 4. Habits and tastes

| Field | Shown as | What to write |
| --- | --- | --- |
| `interests` | "Into *A, B and C*." | Exactly 3, specific ("film photography", not "hobbies"). |
| `values` | "Values *A and B*." | Exactly 2 short nouns: family, status, saving money, faith, self-expression… |
| `shopping_style` | Verb phrase | "waits for sales and compares prices online". |
| `media_habit` | Verb phrase | "posts skate clips on Instagram and TikTok". Must agree with `platforms`. |
| `decision_style` | Verb phrase | "asks the group chat before deciding anything". |
| `quirk` | "Quirk: …" | One small, memorable, specific habit. |
| `music` | "Listens to …" | A genre or scene. |
| `food` | "loves …" | A dish or place: "jollof rice", "burgers from the van by the skate park". |

### 5. Life situation

| Field | Shown as | What to write |
| --- | --- | --- |
| `living` | "Home: *lives with…*" | Start with "lives…" or "shares…". Teenagers live with family. If you write "partner" here, `relationship` must be partnered. |
| `goal_short` | "Goal right now: …" | Something they're working on this month or term. |
| `goal_long` | "Dream: …" | Age-appropriate: a 15-year-old doesn't dream of retiring. |
| `worries` | "Worries about *A and B*." | Exactly 2 noun phrases. Only students worry about exams; only adults worry about rent or job security. |
| `life_context` | "Right now: *is/has/just…*" | What's going on this week. It colours their mood. |
| `stress` | — | 0–1, how stressful their situation is right now (default 0.3). It is scaled by neuroticism. |
| `mood` | — | −1 to 1, how their situation lifts or drags their mood (default 0). |

### 6. Social life

| Field | What to write |
| --- | --- |
| `platforms` | Any of `instagram`, `tiktok`, `group_chat`. Leave it empty (`[]`) only for someone with no social media at all. |
| `posting` | `often`, `sometimes`, `rarely` or `never`. Use **`never` if, and only if, `platforms` is empty.** |

Keep it consistent: a person whose media habit is "lives on TikTok" needs `tiktok`; someone who
"never posts but reads everything" posts `rarely`; nobody without social media worries about being judged online.

### 7. Health and wellbeing

| Field | Example |
| --- | --- |
| `health` | "in good health", "has mild asthma", "has a bad back from years of driving" (bad backs are for adults) |
| `sleep` | "keeps a strict sleep schedule", "stays up too late on the phone" |
| `fitness` | "very active, skates every day", "mostly sedentary". A sports injury goes with an active person. |

### 8. Relationships and home

| Field | Example |
| --- | --- |
| `relationship` | Minors: "single", "has a crush on…", "in a new relationship", "not interested in dating right now". Adults can also be "married", "divorced", "widowed" or "in a long-term relationship". It must agree with `living`. |
| `pets` | "a scruffy dog called Biscuit", "no pets, but desperately wants a cat". If the quirk mentions their dog, give them a dog. |
| `family_closeness` | "very close to their gran", "loves their family but keeps some distance" |

### 9. Background

| Field | Example |
| --- | --- |
| `hometown` | "grew up in this area", "moved here from Ghana at age 8" |
| `family_money` | "grew up with very little money", "grew up comfortable". It doesn't have to match their income now. |
| `formative` | One experience that shaped them: "taught themselves to skate from YouTube videos" |

### 10. Attitudes and beliefs

| Field | Example |
| --- | --- |
| `money_mindset` | "a natural saver", "spends money the moment they get it". Must fit `price_sensitivity`. |
| `brand_attitude` | "skeptical of hype; buys what lasts", "wants whatever the popular seniors are wearing". Must fit `trend_following`. |
| `tech_attitude` | "first to try any new app", "a bit behind on technology" |
| `cause` | A full phrase: "cares about the environment", "isn't into causes or politics" |

---

## Who knows whom

```yaml
      group: g1              # everyone in the same group is a close friend (strong tie)
      family: [Grace]        # relatives in this population: strong tie labelled "family"
      close_to: [Idris]      # extra close friends outside their group (optional)
      knows: [Ren, Viktor]   # acquaintances (weak ties); write each pair on one side only
```

- You only need to write a link on one side. Priya → Grace is enough.
- Only `family:` links are labelled **family**. That label decides who eats together at home and gets the
  highest closeness, so link relatives who actually share a home, and make sure their area, pets and living
  situation agree.
- If anyone in the file lists `knows:`, the acquaintances are exactly what's written. If nobody does, seeded random
  ones are added (`weak_ties_per_agent`).
- Groups of 3–6 work best. Make groups people would really be in: classmates, the parents at the school gate,
  the night-shift crew, the bowls club.
- Names must be unique across **all** communities, because everyone can run together.

## What you don't write

These are computed from what you wrote, the same way as for sampled people: `id`, the persona and the
full profile text (what the model reads), `personality_type`, `temperament` (unless given),
`susceptibility`, the stress and mood baselines, and the segments (`trend_follower`, `price_sensitive`,
`risk_taker`, `influencer`).

## What is checked for you

The build stops with the person's name and the problem if:

- any category field is missing, misspelled or unknown;
- there aren't exactly 3 interests, 2 values and 2 worries, or there are fewer than 4 traits or 5 Big Five scores;
- a value is out of range (traits and Big Five 0–1, stress 0–1, mood −1 to 1, age 10–100);
- `life_stage`, `income`, `chronotype` or `posting` isn't one of the allowed words;
- someone under 18 isn't a student;
- `posting: never` doesn't match empty `platforms`, or a platform isn't in the config;
- a cohort, `family` or `close_to` name doesn't exist;
- two people share a name, or their decision traits are closer than `min_trait_distance`;
- two people have the same occupation and interests, or the same persona.

**Your job** (not machine-checked for written people) is to keep the words consistent with each other
and with the numbers. Before you finish, read each person's profile out loud
(`python -m bellwether population <name>`) and ask: *could this be one real person?*

## Tips for people who feel real

- **Make them different on purpose.** Give each person one thing nobody else has, such as a quirk, a worry or a formative moment.
- **Give them constraints.** Small budgets, exams, night shifts and a strict parent are what make outcomes interesting.
- **Mix the circle.** Include a couple of hype-chasers, a couple of sceptics, one quiet person with a big influence and one loud person with very little.
- **Tie money to life.** A low income with a big budget needs a reason, such as birthday money or a part-time job.
- **Use specifics over adjectives.** "Keeps a list of everything they want to buy, with prices" beats "careful".

---

## Generating more people

Generated people come from the option pools in `bellwether/population/pools.py`. To add many people quickly:

1. Remove the file's `agents:` block (or start a new file with the generator settings: ages, cohorts, trait
   distributions), then run `python -m bellwether export <name> --size N`. This writes N generated people into the file.
2. **Read every one and fix what doesn't ring true.** The generator gets the categories right, but it can't know that
   a parent's teenager should live in the same area, or that a 19-year-old and a 70-year-old are unlikely best
   friends. Re-link family, regroup friends, and fix jobs whose income doesn't fit.
3. To widen the pools, add options there. Most options carry trait affinities, for example
   `"buys on impulse": {"risk_tolerance": 0.8, "conscientiousness": -0.6}`, so they go to the people they fit. Dreams and
   worries have age windows (`DREAM_AGES`, `WORRY_AGES`), so nobody gets one that doesn't fit their age.
4. To add a whole new kind of description, add a field to `Agent` (`models.py`), an entry in `categories.py`, a pool in
   `pools.py`, a pick in `depth.py`, a line in `render_profile`, and a field in `HandAgent` (`handmade.py`), so that
   written people must fill it too.
5. Run `python -m bellwether roster` and `.venv/bin/python -m pytest -q`. `tests/test_categories.py` checks the generator,
   and `tests/test_handmade.py` checks the written files, the combined `all` population and the roster.

The full option lists for each category are in [docs/agent-categories.md](docs/agent-categories.md).
