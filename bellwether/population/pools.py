"""Attribute pools used to make every sampled agent a distinct person.

Nothing here is tied to a scenario: these are the everyday details that
separate one person from another (names, jobs, interests, habits, quirks).
Population configs can override the occupation pool per cohort.
"""

FIRST_NAMES = [
    "Aaliyah", "Aarav", "Abel", "Ada", "Adaeze", "Aditi", "Adrian", "Ahmad", "Aiko", "Aisha",
    "Alejandro", "Alexei", "Alma", "Amara", "Amir", "Ana", "Anders", "Andile", "Ange", "Anika",
    "Ansel", "Arjun", "Ash", "Astrid", "Aurelio", "Ayo", "Bao", "Beatriz", "Bem", "Bilal",
    "Bjorn", "Blessing", "Bo", "Bram", "Bree", "Bruno", "Caio", "Callum", "Camila", "Carmen",
    "Cass", "Cedric", "Chen", "Chidi", "Chloe", "Cyrus", "Dae", "Dalia", "Damian", "Dana",
    "Dara", "Daria", "Dev", "Diego", "Dilnoza", "Dmitri", "Eamon", "Ebo", "Eden", "Efua",
    "Eitan", "Elena", "Eli", "Elif", "Elio", "Ellis", "Emeka", "Emi", "Emre", "Esme",
    "Ezra", "Fai", "Farah", "Felix", "Femi", "Finn", "Flora", "Gabriel", "Gael", "Gia",
    "Gideon", "Greta", "Gus", "Hamza", "Hana", "Hari", "Harper", "Hassan", "Haruto", "Helga",
    "Hiro", "Ibrahim", "Ida", "Ifeoma", "Ilan", "Imani", "Ines", "Ingrid", "Ira", "Isaac",
    "Isla", "Ivan", "Jae", "Jahan", "Jamal", "Jana", "Javier", "Jaya", "Jin", "Joaquin",
    "Jonah", "Jordan", "Jules", "Junaid", "Kai", "Kalani", "Kamal", "Kasia", "Kavya", "Keanu",
    "Kenji", "Khalil", "Kiara", "Kofi", "Lale", "Lana", "Lars", "Laila", "Leah", "Leif",
    "Lena", "Leon", "Levi", "Lin", "Liv", "Lorenzo", "Luca", "Lucia", "Luz", "Mae",
    "Mai", "Malik", "Mana", "Marco", "Mariam", "Mateo", "Maya", "Mehmet", "Mei", "Mila",
    "Milan", "Ming", "Mira", "Moana", "Mo", "Nadia", "Naledi", "Nam", "Nasser", "Nia",
    "Nico", "Nika", "Nils", "Noa", "Noor", "Nuno", "Obi", "Odette", "Olu", "Omar",
    "Oona", "Orla", "Oscar", "Pablo", "Paz", "Pedro", "Pia", "Priya", "Quinn", "Rafael",
    "Rahel", "Rania", "Ravi", "Reem", "Remy", "Rhea", "Rin", "Rio", "Rohan", "Roisin",
    "Rosa", "Rumi", "Ryo", "Saanvi", "Sade", "Salma", "Sami", "Santi", "Sara", "Sasha",
    "Selin", "Seo-yeon", "Shira", "Silas", "Sina", "Sipho", "Siri", "Sol", "Soren", "Suki",
    "Sven", "Tae", "Tala", "Tamar", "Tariq", "Teo", "Thandi", "Theo", "Tiago", "Timur",
    "Tomas", "Uma", "Una", "Valentina", "Vera", "Vikram", "Wei", "Wren", "Xavi", "Ximena",
    "Yara", "Yasmin", "Yuki", "Yusuf", "Zainab", "Zara", "Zeke", "Zhen", "Zola", "Zuri",
]

LOCATIONS = ["city centre", "inner suburb", "outer suburb", "small town", "rural area"]

LIFE_STAGES_BY_AGE = [
    (17, "student"),
    (23, "early career"),
    (31, "settling down"),
    (41, "mid career"),
    (56, "late career"),
    (66, "retired"),
]

OCCUPATIONS = {
    "student": [
        "high school student", "first-year university student", "design student", "nursing student",
        "engineering student", "business student", "art school student", "computer science student",
        "trade apprentice", "music student", "biology student", "part-time barista and student",
    ],
    "early career": [
        "junior software developer", "sales associate", "graphic designer", "warehouse supervisor",
        "teaching assistant", "barber", "social media coordinator", "line cook", "bank teller",
        "junior accountant", "personal trainer", "delivery rider", "lab technician", "content creator",
    ],
    "settling down": [
        "nurse", "electrician", "marketing manager", "primary school teacher", "data analyst",
        "physiotherapist", "small-business owner", "civil engineer", "police officer", "pharmacist",
        "UX researcher", "logistics coordinator",
    ],
    "mid career": [
        "operations manager", "dentist", "high school teacher", "real estate agent", "architect",
        "IT consultant", "restaurant owner", "plumber", "HR manager", "journalist", "veterinarian",
        "construction foreman",
    ],
    "late career": [
        "school principal", "senior accountant", "truck driver", "university lecturer",
        "store manager", "family doctor", "insurance broker", "machinist", "civil servant",
        "farm owner",
    ],
    "retired": [
        "retired teacher", "retired engineer", "retired nurse", "retired shop owner",
        "retired bus driver", "retired banker", "retired chef", "retired soldier",
    ],
}

INTERESTS = [
    "streetwear", "thrift shopping", "sneaker collecting", "indie music", "hip-hop", "K-pop",
    "football", "basketball", "skateboarding", "running", "gym training", "yoga", "hiking",
    "fishing", "gardening", "cooking", "baking", "coffee", "craft beer", "video games",
    "tabletop games", "anime", "film photography", "street photography", "painting", "drawing",
    "knitting", "woodworking", "car tuning", "cycling", "travel", "camping", "reading novels",
    "true crime podcasts", "history", "astronomy", "coding side projects", "crypto", "investing",
    "fashion magazines", "vintage furniture", "houseplants", "DIY repairs", "volunteering",
    "church community", "local politics", "stand-up comedy", "theatre", "dance", "chess",
    "board sports", "birdwatching", "pets", "home décor", "makeup", "tattoos", "festivals",
    "language learning", "meditation",
]

VALUES = [
    "family", "loyalty", "independence", "self-expression", "status", "saving money", "fairness",
    "tradition", "adventure", "comfort", "quality", "community", "sustainability", "ambition",
    "fun", "security", "authenticity", "belonging", "curiosity", "faith",
]

# Habits carry trait affinities (+1 fits a high value, -1 fits a low value) so the
# details picked for a person agree with their traits instead of contradicting them.
SHOPPING_STYLES = {
    "hunts for deals and waits for sales": {"price_sensitivity": 1},
    "buys on impulse when something catches their eye": {"risk_tolerance": 1, "price_sensitivity": -1},
    "researches reviews thoroughly before buying": {"risk_tolerance": -1},
    "sticks to a few trusted brands": {"risk_tolerance": -1, "trend_following": -0.5},
    "buys mostly second-hand": {"price_sensitivity": 1, "trend_following": -0.5},
    "only buys what they need, when they need it": {"price_sensitivity": 0.5, "trend_following": -1},
    "likes being first to own new things": {"risk_tolerance": 1, "trend_following": 0.5},
    "asks friends before buying anything": {"trend_following": 1, "risk_tolerance": -0.5},
    "splurges occasionally, then cuts back": {"price_sensitivity": 0.3},
    "budgets every purchase in advance": {"price_sensitivity": 1, "risk_tolerance": -0.5},
    "buys gifts more often than things for themselves": {"social_influence": 0.5},
    "prefers small local makers over big brands": {"trend_following": -0.5},
}

MEDIA_HABITS = {
    "scrolls Instagram daily": {"trend_following": 0.7},
    "lives on TikTok": {"trend_following": 1},
    "mostly uses group chats": {"social_influence": 0.5},
    "reads news sites every morning": {"trend_following": -0.3},
    "watches YouTube reviews": {"risk_tolerance": -0.5},
    "barely uses social media": {"trend_following": -1, "social_influence": -0.5},
    "active in Discord communities": {"social_influence": 0.5},
    "follows a few influencers closely": {"trend_following": 1},
    "listens to podcasts on commutes": {},
    "checks Reddit threads before deciding": {"risk_tolerance": -0.5},
    "hears about things through word of mouth": {"trend_following": 0.3},
    "posts regularly and has a following": {"social_influence": 1},
}

DECISION_STYLES = {
    "decides quickly on gut feeling": {"risk_tolerance": 1},
    "overthinks and often delays": {"risk_tolerance": -1},
    "weighs pros and cons on paper": {"risk_tolerance": -0.5, "price_sensitivity": 0.3},
    "goes along with the group": {"trend_following": 1},
    "asks a partner or parent first": {"social_influence": -0.5},
    "decides alone and sticks to it": {"trend_following": -1, "social_influence": 0.3},
    "changes their mind easily": {"trend_following": 0.7},
    "needs to see proof from others first": {"trend_following": 0.7, "risk_tolerance": -0.7},
    "is stubborn once they commit": {"trend_following": -0.7},
    "follows routine and avoids surprises": {"risk_tolerance": -1},
}

QUIRKS = [
    "always early to everything", "collects concert wristbands", "never leaves the house without headphones",
    "keeps a spreadsheet for everything", "remembers everyone's birthday", "talks about their dog constantly",
    "refuses to pay full price on principle", "loves telling people about new finds", "hates crowds",
    "wears the same style every day", "jokes through awkward moments", "is the group's unofficial organiser",
    "keeps receipts in a shoebox", "quietly judges logos", "has strong opinions about fabric quality",
    "never posts but reads everything", "volunteers for every committee", "is famously indecisive at menus",
    "loves limited editions", "distrusts anything that's hyped", "always asks 'is it worth it?'",
    "buys matching items with their best friend", "tracks every package obsessively", "cries at films",
    "has a side hustle selling stuff online", "rearranges their room monthly", "is learning to sew",
    "won't buy anything without touching it first", "screenshots everything", "always has snacks to share",
    "keeps a gratitude journal", "knows every shortcut in town", "can't resist a good story behind a product",
    "returns about half of what they order", "plans holidays a year ahead", "texts in voice notes only",
    "gives honest, blunt feedback", "is everyone's tech support", "follows the weather obsessively",
    "has never missed a school or work event", "sketches on every napkin", "always roots for the underdog",
    "shows up with a new hobby every month", "keeps old clothes for sentimental reasons",
    "sends memes at 2am", "is suspicious of discounts", "loves anything handmade", "reads the fine print",
]

# Words used to describe trait levels in the persona text, low to high (5 levels).
TRAIT_LADDERS = {
    "risk_tolerance": [
        "very cautious, avoids anything uncertain",
        "prefers safe, proven choices",
        "takes measured risks",
        "comfortable trying new and unproven things",
        "loves taking chances on the new and untested",
    ],
    "price_sensitivity": [
        "rarely looks at price",
        "notices price but it seldom decides things",
        "weighs price against value",
        "watches every dollar",
        "extremely price-sensitive; price often decides for them",
    ],
    "trend_following": [
        "ignores what others do and decides independently",
        "only mildly influenced by trends",
        "somewhat influenced by what friends do",
        "often follows what friends and online circles do",
        "strongly copies what friends and popular people do",
    ],
    "social_influence": [
        "rarely shares opinions; others seldom follow them",
        "shares opinions occasionally; modest sway",
        "has some sway in their circle",
        "often sets the tone in their circle",
        "a trendsetter; friends often follow their lead",
    ],
}

# Quirks that only fit some trait profiles; unlisted quirks fit anyone.
QUIRK_AFFINITY = {
    "refuses to pay full price on principle": {"price_sensitivity": 1},
    "loves telling people about new finds": {"social_influence": 1},
    "never posts but reads everything": {"social_influence": -1},
    "loves limited editions": {"trend_following": 0.7, "risk_tolerance": 0.5},
    "distrusts anything that's hyped": {"trend_following": -1},
    "always asks 'is it worth it?'": {"price_sensitivity": 1},
    "is suspicious of discounts": {"price_sensitivity": -0.7},
    "buys matching items with their best friend": {"trend_following": 1},
    "is the group's unofficial organiser": {"social_influence": 1},
    "hates crowds": {"trend_following": -0.5},
    "shows up with a new hobby every month": {"risk_tolerance": 0.7},
    "plans holidays a year ahead": {"risk_tolerance": -0.7},
    "has a side hustle selling stuff online": {"risk_tolerance": 0.5},
    "keeps a spreadsheet for everything": {"risk_tolerance": -0.5, "price_sensitivity": 0.5},
    "gives honest, blunt feedback": {"social_influence": 0.5},
}

# Income mix multipliers by life stage (applied to the population's income weights).
INCOME_BY_LIFE_STAGE = {
    "student": {"low": 2.5, "mid": 0.6, "high": 0.1},
    "early career": {"low": 1.4, "mid": 1.0, "high": 0.3},
    "settling down": {"low": 0.9, "mid": 1.2, "high": 0.8},
    "mid career": {"low": 0.6, "mid": 1.1, "high": 1.4},
    "late career": {"low": 0.6, "mid": 1.0, "high": 1.5},
    "retired": {"low": 1.2, "mid": 1.1, "high": 0.5},
}

# Interests that don't fit someone under 18.
ADULT_INTERESTS = {"craft beer", "investing", "crypto", "tattoos"}

# ---- deeper persona details ---------------------------------------------------------------

LIVING = {
    "student": ["lives with both parents and a younger sibling", "lives with mum and an older brother",
                "lives with dad and a stepmum", "lives with grandparents", "lives with parents, only child",
                "shares a flat with two other students", "lives in student halls"],
    "early career": ["shares a flat with two roommates", "lives alone in a small studio", "lives with their partner",
                     "still lives with their parents to save money", "rents a room in a shared house"],
    "settling down": ["lives with their partner and a toddler", "lives with their partner, no kids yet",
                      "lives alone with a cat", "lives with their partner and two young kids"],
    "mid career": ["lives with their partner and two teenagers", "is a single parent of one teenager",
                   "lives with their partner; kids just left home", "lives alone after a divorce"],
    "late career": ["lives with their partner; grown kids visit on Sundays", "lives alone, close to their sister",
                    "lives with their partner and an elderly parent"],
    "retired": ["lives with their partner", "lives alone, widowed", "lives with their daughter's family"],
}

GOALS_SHORT = {
    "student": ["pass this term's exams", "save up for new trainers", "get into the school team", "finish a portfolio",
                "make more friends this year", "get their driving licence", "earn some money from a weekend job"],
    "early career": ["get a pay rise", "move into a nicer flat", "pay off a credit card", "find a new job",
                     "run a 10k", "save for a holiday"],
    "retired": ["keep the garden in shape", "see the grandkids more often", "keep walking every day",
                "take a coach trip with friends", "learn to use their new phone properly"],
    "_": ["take a proper holiday", "fix up the house", "get healthier", "spend more time with family",
          "save for retirement", "learn a new skill"],
}
# Dreams and worries that only make sense from a certain age.
ADULT_ONLY_DREAMS = {"retire somewhere warm"}
ADULT_ONLY_WORRIES = {"job security", "rent going up"}
MEDIA_NEEDS_PLATFORM = {"lives on TikTok": "tiktok", "scrolls Instagram daily": "instagram"}
GOALS_LONG = ["start their own business", "become a nurse", "work in fashion or design", "own a home",
              "travel the world", "become financially independent", "raise a happy family", "become a known creator online",
              "get into a top university", "retire somewhere warm", "make a difference in their community",
              "see the grandkids grow up", "enjoy a long, quiet retirement", "write down the family history"]
# (youngest, oldest) age a dream or worry makes sense for; anything not listed fits every age.
DREAM_AGES = {
    "get into a top university": (0, 25), "become a nurse": (0, 35), "work in fashion or design": (0, 35),
    "become a known creator online": (0, 40), "raise a happy family": (0, 45), "start their own business": (0, 55),
    "become financially independent": (0, 55), "own a home": (0, 60), "travel the world": (0, 62),
    "retire somewhere warm": (35, 64), "see the grandkids grow up": (55, 100),
    "enjoy a long, quiet retirement": (58, 100), "write down the family history": (55, 100),
}
WORRY_AGES = {
    "fitting in with friends": (0, 25), "missing out on what friends are doing": (0, 35), "how they look": (0, 50),
    "being judged online": (0, 50), "not having a clear plan for the future": (0, 45), "their weight": (0, 60),
    "job security": (18, 64), "their parents' health": (0, 70), "their own health": (50, 100),
    "being a burden on their family": (65, 100), "their pension not stretching far enough": (60, 100),
}


def fits_age(table: dict[str, tuple[int, int]], item: str, age: int) -> bool:
    lo, hi = table.get(item, (0, 200))
    return lo <= age <= hi

WORRIES = ["money being tight", "fitting in with friends", "exams and grades", "their parents' health", "job security",
           "how they look", "missing out on what friends are doing", "rent going up", "being judged online",
           "not having a clear plan for the future", "a friend who has been distant lately", "their weight", "loneliness",
           "their own health", "being a burden on their family", "their pension not stretching far enough"]
MINOR_LIVING = ["lives with both parents and a younger sibling", "lives with mum and an older brother",
                "lives with dad and a stepmum", "lives with grandparents", "lives with parents, only child",
                "lives with mum, dad and two little sisters"]

LIFE_CONTEXT = [  # (situation, stress 0-1, mood shift -1..1)
    ("an ordinary, fairly calm week", 0.2, 0.0),
    ("exam week is coming up", 0.6, -0.1),
    ("just got some good news and feels on a high", 0.15, 0.3),
    ("had a falling out with a close friend", 0.5, -0.3),
    ("is short on money until next payday", 0.55, -0.15),
    ("is busy with lots of commitments this week", 0.5, -0.05),
    ("recently started something new and is excited", 0.3, 0.2),
    ("is getting over a cold and feels tired", 0.35, -0.15),
    ("has a birthday coming up soon", 0.2, 0.2),
    ("is going through a quiet, slightly lonely patch", 0.4, -0.2),
]

MUSIC = ["hip-hop", "pop", "indie rock", "R&B", "drill", "K-pop", "jazz", "country", "EDM", "classic rock",
         "afrobeats", "lo-fi", "metal", "reggaeton", "folk"]
FOODS = ["burgers", "sushi", "pizza", "their mum's cooking", "spicy noodles", "fried chicken", "salads", "curry",
         "tacos", "pastries", "kebabs", "pho"]

TEMPERAMENT = {  # from the strongest Big Five pole
    ("extraversion", 1): "loud, warm and the first to start a conversation",
    ("extraversion", 0): "quiet and reserved; opens up only to close friends",
    ("agreeableness", 1): "kind and easy-going; hates conflict",
    ("agreeableness", 0): "blunt and a bit competitive; doesn't mind disagreeing",
    ("conscientiousness", 1): "organised and reliable; sticks to plans",
    ("conscientiousness", 0): "spontaneous and a bit disorganised; often late",
    ("neuroticism", 1): "worries a lot and takes things to heart",
    ("neuroticism", 0): "calm and hard to rattle",
    ("openness", 1): "curious and up for new experiences",
    ("openness", 0): "likes what they know and keeps to routines",
}

# ---- group 7: health & wellbeing -------------------------------------------------------------
HEALTH = ["in good health", "very rarely gets sick", "gets tired easily", "has mild asthma",
          "recovering from a sports injury", "gets migraines now and then", "managing a long-term condition",
          "has bad allergies in spring", "has a bad back", "fit and healthy but eats badly"]
SLEEP = {  # trait affinities like the habits above
    "sleeps well": {"neuroticism": -1},
    "a light sleeper": {"neuroticism": 0.5},
    "struggles to fall asleep": {"neuroticism": 1},
    "never gets enough sleep": {"conscientiousness": -0.7},
    "sleeps in whenever possible": {"conscientiousness": -1},
    "keeps a strict sleep schedule": {"conscientiousness": 1},
}
FITNESS = {
    "very active, works out most days": {"conscientiousness": 0.8, "extraversion": 0.3},
    "fairly active": {},
    "not very active": {"conscientiousness": -0.4},
    "mostly sedentary": {"conscientiousness": -0.8},
}

# ---- group 8: relationships & home -----------------------------------------------------------
RELATIONSHIP_MINOR = ["single", "has a crush on someone at school", "in a new relationship",
                      "just went through a breakup", "not interested in dating right now"]
RELATIONSHIP_ADULT = ["single", "dating casually", "in a long-term relationship", "married",
                      "recently separated"]
PETS = ["no pets", "no pets", "a dog", "a cat", "two cats", "a rabbit", "fish", "a dog and a cat", "a hamster"]
FAMILY_CLOSENESS = {
    "very close to their family": {"agreeableness": 0.8},
    "close to one parent in particular": {},
    "has a tense relationship with their family": {"agreeableness": -0.8, "neuroticism": 0.5},
    "is the glue that keeps their family together": {"agreeableness": 1, "conscientiousness": 0.5},
    "loves their family but keeps some distance": {"agreeableness": -0.3},
}

# ---- group 9: background ------------------------------------------------------------------------
HOMETOWN = ["grew up in this same area", "grew up in this same area", "moved here from another city a few years ago",
            "grew up in a small town nearby", "moved here from abroad as a child", "moved around a lot growing up"]
FAMILY_MONEY = ["grew up with very little money", "grew up in an average household", "grew up comfortable",
                "grew up well-off"]
FORMATIVE = ["was bullied as a kid and is careful who they trust", "had a coach who changed their life",
             "grew up looking after younger siblings", "lost a grandparent they were very close to",
             "won a competition they're still proud of", "watched a parent build a small business",
             "changed schools several times", "spent summers helping in a family shop",
             "had a long illness as a child", "was the first in their family to try something big",
             "had a best friend move away", "grew up in a very strict household"]

# ---- group 10: attitudes & beliefs ----------------------------------------------------------------
MONEY_MINDSET = {
    "a natural saver": {"price_sensitivity": 1, "risk_tolerance": -0.5},
    "a spender who lives in the moment": {"price_sensitivity": -1, "risk_tolerance": 0.7},
    "careful with money but treats themselves sometimes": {"price_sensitivity": 0.4},
    "anxious about money": {"price_sensitivity": 0.8, "neuroticism": 0.8},
    "doesn't think about money much": {"price_sensitivity": -0.8},
}
BRAND_ATTITUDE = {
    "loves discovering small, independent brands": {"trend_following": -0.3, "openness": 0.8},
    "loyal to big, well-known brands": {"risk_tolerance": -0.8},
    "skeptical of hype and marketing": {"trend_following": -1},
    "buys what friends and influencers recommend": {"trend_following": 1},
    "doesn't care about brands at all": {"trend_following": -0.6, "price_sensitivity": 0.4},
}
TECH_ATTITUDE = {
    "first to try new apps and gadgets": {"risk_tolerance": 0.8, "openness": 0.6},
    "uses tech like everyone else": {},
    "a bit behind on technology": {"openness": -0.8, "risk_tolerance": -0.4},
}
CAUSES = ["cares about the environment", "cares about animal welfare", "cares about mental health awareness",
          "cares about fairness and equality", "cares about their local community",
          "isn't into causes or politics", "cares about education and young people", "cares about health and fitness",
          "cares about their faith and religious community"]
