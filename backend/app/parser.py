"""Rule-based natural-language query parser.

Turns e.g. "senior backend developers with 5+ years in India" into
{role: Backend Developer, seniority: Senior, min_years: 5, country: India}.
Known roles/skills/domains come from the dictionaries below; countries,
locations and extra skill phrases are looked up in the loaded data (Vocab).
"""
import re
from dataclasses import dataclass, field, asdict

# canonical role -> (query phrases, title terms matched against candidate titles)
ROLES = {
    "Software Engineer": (["software engineer", "software developer", "software development engineer", "sde", "swe"],
                          ["software engineer", "software developer", "software development engineer", "sde", "swe",
                           "software engineering", "programmer", "application developer"]),
    "Backend Developer": (["backend developer", "backend engineer", "back-end developer", "back-end engineer",
                           "back end developer", "back end engineer", "server side developer", "backend"],
                          ["backend", "back-end", "back end", "server side", "server-side", "api developer"]),
    "Frontend Developer": (["frontend developer", "frontend engineer", "front-end developer", "front-end engineer",
                            "front end developer", "front end engineer", "ui developer", "ui engineer", "frontend"],
                           ["frontend", "front-end", "front end", "ui developer", "ui engineer"]),
    "Full Stack Developer": (["full stack developer", "full-stack developer", "fullstack developer",
                              "full stack engineer", "full-stack engineer", "fullstack engineer", "full stack"],
                             ["full stack", "full-stack", "fullstack"]),
    "Mobile Developer": (["mobile developer", "mobile engineer", "android developer", "ios developer", "app developer"],
                         ["mobile", "android", "ios", "app developer"]),
    "Web Developer": (["web developer", "web designer"], ["web developer", "web designer", "webmaster"]),
    "Data Scientist": (["data scientist"], ["data scientist", "data science"]),
    "Data Engineer": (["data engineer"], ["data engineer", "big data", "etl developer"]),
    "Data Analyst": (["data analyst", "analytics"], ["data analyst", "analytics", "bi analyst", "business intelligence"]),
    "Machine Learning Engineer": (["machine learning engineer", "ml engineer", "ai engineer", "ai/ml engineer"],
                                  ["machine learning", "ml engineer", "ai engineer", "deep learning"]),
    "DevOps Engineer": (["devops engineer", "devops", "site reliability engineer", "sre", "cloud engineer", "platform engineer"],
                        ["devops", "site reliability", "sre", "cloud engineer", "platform engineer", "infrastructure engineer"]),
    "QA Engineer": (["qa engineer", "test engineer", "qa", "quality assurance", "sdet", "tester", "automation tester"],
                    ["qa", "quality assurance", "test engineer", "sdet", "tester", "test automation"]),
    "Product Manager": (["product manager", "product owner"], ["product manager", "product owner", "product management"]),
    "Project Manager": (["project manager", "program manager"], ["project manager", "program manager", "delivery manager"]),
    "UI/UX Designer": (["ui/ux designer", "ux designer", "ui designer", "product designer"],
                       ["ux", "ui/ux", "ui designer", "product designer", "interaction designer"]),
    "Solutions Architect": (["solution architect", "solutions architect", "software architect"],
                       ["architect"]),
}
GENERIC_DEV_TERMS = ["developer", "engineer", "programmer", "dev"]

# canonical skill -> aliases (matched with token boundaries)
SKILLS = {
    "Python": ["python"], "Java": ["java"], "JavaScript": ["javascript", "js", "es6"],
    "TypeScript": ["typescript"], "React": ["react", "react.js", "reactjs"], "Angular": ["angular", "angularjs"],
    "Vue": ["vue", "vue.js", "vuejs"], "Node.js": ["node.js", "nodejs", "node"], "Express": ["express", "express.js", "expressjs"],
    "MongoDB": ["mongodb", "mongo"], "PostgreSQL": ["postgresql", "postgres"], "MySQL": ["mysql"], "SQL": ["sql"],
    "AWS": ["aws", "amazon web services"], "Azure": ["azure"], "GCP": ["gcp", "google cloud"],
    "Docker": ["docker"], "Kubernetes": ["kubernetes", "k8s"], "Go": ["golang"], "C++": ["c++", "cpp"],
    "C#": ["c#", "csharp"], ".NET": [".net", "dotnet", "asp.net"], "PHP": ["php"], "Laravel": ["laravel"],
    "Django": ["django"], "Flask": ["flask"], "FastAPI": ["fastapi"], "Spring Boot": ["spring boot", "spring"],
    "Ruby on Rails": ["ruby on rails", "rails", "ruby"], "Kotlin": ["kotlin"], "Swift": ["swift"],
    "Flutter": ["flutter"], "React Native": ["react native"], "HTML": ["html", "html5"], "CSS": ["css", "css3"],
    "Tailwind CSS": ["tailwind"], "Redux": ["redux"], "GraphQL": ["graphql"], "REST APIs": ["rest api", "rest apis", "restful"],
    "Microservices": ["microservices"], "Machine Learning": ["machine learning"], "Deep Learning": ["deep learning"],
    "NLP": ["nlp", "natural language processing"], "TensorFlow": ["tensorflow"], "PyTorch": ["pytorch"],
    "Pandas": ["pandas"], "Spark": ["spark", "pyspark"], "Kafka": ["kafka"], "Redis": ["redis"],
    "Elasticsearch": ["elasticsearch"], "Linux": ["linux"], "Git": ["git"], "Jenkins": ["jenkins"],
    "Terraform": ["terraform"], "Power BI": ["power bi", "powerbi"], "Tableau": ["tableau"], "Excel": ["excel"],
    "Salesforce": ["salesforce"], "SAP": ["sap"], "Figma": ["figma"], "Selenium": ["selenium"], "Rust": ["rust"],
    "Scala": ["scala"], "Next.js": ["next.js", "nextjs"], "Apache": ["apache"],
}
STACKS = {
    "mern": ["MongoDB", "Express", "React", "Node.js"],
    "mean": ["MongoDB", "Express", "Angular", "Node.js"],
    "mevn": ["MongoDB", "Express", "Vue", "Node.js"],
    "lamp": ["Linux", "Apache", "MySQL", "PHP"],
}
DOMAINS = {
    "Fintech": ["fintech", "fin-tech", "financial technology", "payments", "payment", "banking", "bank",
                "financial services", "lending", "neobank", "wealth management", "trading", "capital markets",
                "insurtech", "credit card", "stripe", "paypal", "razorpay", "paytm", "mastercard"],
    "Banking": ["banking", "bank", "retail banking", "investment banking", "commercial banking", "financial services",
                "lending", "credit union", "neobank", "wealth management", "capital markets"],
    "IT / Software": ["information technology", "it services", "software development", "software company",
                      "computer software", "it consulting", "software engineering", "saas", "cloud services",
                      "infosys", "tcs", "tata consultancy", "wipro", "hcl", "accenture", "cognizant", "capgemini"],
    "Healthcare": ["healthcare", "health care", "healthtech", "medical", "hospital", "pharma", "pharmaceutical", "clinical"],
    "E-commerce": ["e-commerce", "ecommerce", "online retail", "marketplace", "amazon", "flipkart", "shopify"],
    "EdTech": ["edtech", "education technology", "e-learning", "elearning", "online learning"],
    "SaaS": ["saas", "software as a service", "b2b software"],
    "Gaming": ["gaming", "game development", "video games", "game studio"],
    "Insurance": ["insurance", "insurtech"],
    "Telecom": ["telecom", "telecommunications"],
    "Logistics": ["logistics", "supply chain", "shipping", "freight"],
    "Automotive": ["automotive", "automobile"],
    "Retail": ["retail"],
    "Consulting": ["consulting", "consultancy"],
}
DOMAIN_QUERY_WORDS = {  # words in a query that select a domain
    "fintech": "Fintech", "fin-tech": "Fintech", "banking": "Banking", "payments": "Fintech", "finance": "Fintech",
    "financial services": "Fintech", "it services": "IT / Software", "information technology": "IT / Software",
    "software industry": "IT / Software", "software companies": "IT / Software", "it industry": "IT / Software", "healthcare": "Healthcare", "health care": "Healthcare", "healthtech": "Healthcare",
    "medical": "Healthcare", "e-commerce": "E-commerce", "ecommerce": "E-commerce", "edtech": "EdTech",
    "saas": "SaaS", "gaming": "Gaming", "insurance": "Insurance", "telecom": "Telecom", "logistics": "Logistics",
    "automotive": "Automotive", "retail": "Retail", "consulting": "Consulting",
}
COUNTRY_ALIASES = {"usa": "united states", "us": "united states", "u.s.": "united states", "america": "united states",
                   "uk": "united kingdom", "u.k.": "united kingdom", "england": "united kingdom", "britain": "united kingdom",
                   "uae": "united arab emirates", "holland": "netherlands"}
CITY_ALIASES = {"bangalore": "bengaluru", "bombay": "mumbai", "gurgaon": "gurugram", "madras": "chennai", "calcutta": "kolkata"}
SENIORITY = {"senior": "Senior", "sr": "Senior", "sr.": "Senior", "junior": "Junior", "jr": "Junior", "jr.": "Junior",
             "lead": "Lead", "principal": "Principal", "staff": "Staff", "head": "Head", "mid-level": "Mid", "mid level": "Mid",
             "entry level": "Entry", "entry-level": "Entry", "fresher": "Entry", "intern": "Intern"}
FILLER = {"find", "show", "me", "get", "search", "list", "give", "looking", "look", "for", "need", "want", "hire", "hiring",
          "candidates", "candidate", "people", "profiles", "profile", "someone", "with", "who", "has", "have", "having",
          "worked", "working", "work", "experience", "experienced", "exp", "of", "and", "or", "the", "a", "an", "in",
          "at", "on", "years", "year", "yrs", "yr", "stack", "skills", "skill", "knowledge", "background", "strong",
          "good", "expert", "expertise", "proficient", "plus", "please", "all", "any", "some", "that", "are", "is",
          "be", "based", "located", "hello", "hi", "hey", "test", "thanks", "thank", "you", "living", "from", "to", "currently", "previously", "companies", "company",
          "industry", "domain", "sector", "using", "know", "knows", "can", "i", "we", "+", "-", ",", "&", "/"}
NO_SINGULAR = {"sales", "devops", "aws", "ios", "js", "analytics", "ops", "logistics", "process", "business", "systems",
               "news", "access", "express", "nodejs", "reactjs", "vuejs", "angularjs", "nextjs", "kubernetes"}


# words that mark a phrase as an organisation name rather than a job title
COMPANY_HINTS = {"bank", "ltd", "limited", "inc", "corp", "corporation", "llc", "llp", "pvt", "private", "gmbh", "plc",
                 "technologies", "technology", "solutions", "systems", "labs", "group", "holdings", "industries",
                 "services", "consultancy", "software", "university", "college", "hospital", "motors", "insurance",
                 "finance", "capital", "ventures", "infotech", "infosystems", "enterprises", "co", "company"}
NUMBER_WORDS = {w: str(i) for i, w in enumerate(
    "zero one two three four five six seven eight nine ten eleven twelve thirteen fourteen fifteen sixteen "
    "seventeen eighteen nineteen twenty".split())}
EXACT_TOLERANCE = 0.1   # "5 years" matches 4.9 – 5.1
APPROX_TOLERANCE = 1.0  # "about 5 years" matches 4 – 6


@dataclass
class Vocab:
    countries: set = field(default_factory=set)        # lower-case country names in data
    skills: set = field(default_factory=set)           # lower-case skill phrases seen in data
    location_exists: callable = lambda term: False     # does any candidate location contain this term?
    count: callable = lambda kind, phrase: 0           # candidates matching phrase as 'name' / 'company' / 'title'
    correct_company: callable = lambda phrase: None    # closest company phrase present in the data, if any

    def company_exists(self, phrase):
        return self.count("company", phrase) > 0


@dataclass
class ParsedQuery:
    role: str | None = None
    role_terms: list = field(default_factory=list)
    seniority: str | None = None
    skills: list = field(default_factory=list)        # [{"name": str, "aliases": [...]}]
    skills_mode: str = "any"                          # any = at least one skill, all = every skill
    stack: str | None = None
    stack_skills: list = field(default_factory=list)  # MERN etc.: at least 2 of these (or the stack name)
    experience: dict | None = None                    # {"op": exact|min|gt|max|lt|range|approx, "value"/"min"/"max"}
    min_years: float | None = None
    max_years: float | None = None
    min_exclusive: bool = False                       # "more than 5" -> years > 5
    max_exclusive: bool = False                       # "less than 5" -> years < 5
    experience_label: str | None = None
    name: str | None = None
    name_tokens: list = field(default_factory=list)
    country: str | None = None
    location: str | None = None
    company: str | None = None
    company_status: str = "any"                       # any | current | former
    company_typed: str | None = None                  # what the user typed, when spelling was corrected
    domain: str | None = None
    domain_terms: list = field(default_factory=list)
    keywords: list = field(default_factory=list)

    def is_empty(self):
        return not any([self.role, self.seniority, self.skills, self.stack, self.min_years is not None,
                        self.max_years is not None,
                        self.name, self.country, self.location, self.company, self.domain, self.keywords])

    def summary(self):
        d = {"name": self.name, "role": self.role, "seniority": self.seniority,
             "skills": [s["name"] for s in self.skills],
             "stack": f"{self.stack.upper()} ({', '.join(s['name'] for s in self.stack_skills)})" if self.stack else None,
             "experience": self.experience_label, "country": self.country, "location": self.location,
             "company": self.company,
             "company_status": {"current": "Current employees", "former": "Former employees",
                                "any": "Current or former"}[self.company_status] if self.company else None,
             "spelling": f"{self.company_typed} → {self.company}" if self.company_typed else None,
             "domain": self.domain, "keywords": self.keywords}
        return {k: v for k, v in d.items() if v not in (None, [], "")}


def _phrase_re(phrases):
    alts = "|".join(re.escape(p) for p in sorted(phrases, key=len, reverse=True))
    return re.compile(rf"(?<![a-z0-9])(?:{alts})(?:s|es)?(?![a-z0-9+#])")


_ROLE_RES = [(name, _phrase_re(q), t) for name, (q, t) in ROLES.items()]
_SKILL_RES = [(name, _phrase_re(a), a) for name, a in SKILLS.items()]
_DOMAIN_RE = _phrase_re(DOMAIN_QUERY_WORDS)
_SENIORITY_RE = _phrase_re(SENIORITY)
_YRS = r"(?:years?|yrs?)"
_N = r"(\d+(?:\.\d+)?)"
_END = r"(?= with | who | having | and | in | based | at |,|$| $)"

# (pattern, kind): first match wins, so specific phrasings come before the bare "N years"
EXPERIENCE_PATTERNS = [
    (rf"between {_N} (?:and|to|-) {_N} ?{_YRS}", "range"),
    (rf"{_N} ?(?:-|–|to) ?{_N} ?{_YRS}", "range"),
    (rf"(?:at least|atleast|minimum(?: of)?|min\.?|no less than|not less than) {_N} ?\+? ?{_YRS}", "min"),
    (rf"(?:more than|over|above|greater than|in excess of) {_N} ?\+? ?{_YRS}", "gt"),
    (rf"(?:less than|under|below|fewer than) {_N} ?{_YRS}", "lt"),
    (rf"(?:up to|upto|at most|maximum(?: of)?|max\.?|no more than|not more than) {_N} ?{_YRS}", "max"),
    (rf"{_N} ?(?:\+|plus) ?{_YRS}", "min"),
    (rf"{_N} ?{_YRS} ?(?:\+|or more|or above|and above|plus)", "min"),
    (rf"{_N} ?{_YRS} ?(?:or less|or fewer|or below|and below)", "max"),
    (rf"(?:around|about|approximately|approx\.?|roughly|~) ?{_N} ?{_YRS}", "approx"),
    (rf"(?:exactly|precisely|just) {_N} ?{_YRS}", "exact"),
    (rf"{_N} ?{_YRS}", "exact"),
]
_EXP_TAIL = r"(?: of)?(?: (?:professional |relevant |work |working |industry |total )?(?:experience|exp))?"

_NAME_CUE_RE = re.compile(r"(?:named|called|by the name(?: of)?|with the name|whose name is|name is)\s+"
                          r"([a-z][a-z .'-]*?)" + _END)
_COMPANY_CUE_RE = re.compile(
    r"(?:(?P<current>current(?:ly)? (?:employees?|employed|working|staff|people|candidates|engineers|developers)?"
    r" ?(?:at|of|in|with|for|by)|currently at|presently at|(?:employees?|staff|employed) (?:of|at|by)"
    r"|works? (?:at|for)|working (?:at|for))"
    r"|(?P<former>former(?:ly)? (?:employees? |staff |people )?(?:at|of|with|from|worked at)"
    r"|previously (?:worked )?(?:at|with|for)|(?<![a-z])ex[- ]|used to work (?:at|for)|alumni of"
    r"|past employees? (?:of|at))"
    r"|(?P<any>(?:has |have |who )?worked (?:at|for)|experience at|employment at)"
    r"|(?P<weak>\bat|\bfrom))"
    r" ?(?P<co>[a-z0-9&.' -]+?)" + _END)


def _cut(text, m):
    return text[:m.start()] + " , " + text[m.end():]


def _title(s):
    return " ".join(w if w.isupper() else w[:1].upper() + w[1:] for w in s.split())


def _num(x):
    return f"{x:g}"


def _singular(word):
    if word in NO_SINGULAR or len(word) <= 3:
        return word
    if word.endswith("ies"):
        return word[:-3] + "y"
    if word.endswith("s") and not word.endswith("ss"):
        return word[:-1]
    return word


def apply_experience(pq, exp):
    """Set the year bounds and label on pq from {"op": ..., "value" | "min"/"max": ...}."""
    op = exp["op"]
    x = exp.get("value")
    pq.experience = dict(exp)
    pq.min_exclusive = pq.max_exclusive = False
    pq.min_years = pq.max_years = None
    if op == "range":
        pq.min_years, pq.max_years = exp["min"], exp["max"]
        label = f"{_num(exp['min'])}\u2013{_num(exp['max'])} yrs"
    elif op == "min":
        pq.min_years, label = x, f"{_num(x)}+ yrs"
    elif op == "gt":
        pq.min_years, pq.min_exclusive, label = x, True, f"more than {_num(x)} yrs"
    elif op == "max":
        pq.max_years, label = x, f"up to {_num(x)} yrs"
    elif op == "lt":
        pq.max_years, pq.max_exclusive, label = x, True, f"less than {_num(x)} yrs"
    elif op == "approx":
        pq.min_years, pq.max_years = max(0.0, x - APPROX_TOLERANCE), x + APPROX_TOLERANCE
        label = f"about {_num(x)} yrs ({_num(pq.min_years)}\u2013{_num(pq.max_years)})"
    else:  # exact
        pq.min_years, pq.max_years = max(0.0, x - EXACT_TOLERANCE), x + EXACT_TOLERANCE
        label = f"exactly {_num(x)} yrs (\u00b1{_num(EXACT_TOLERANCE)})"
    pq.experience_label = label


def _parse_experience(text, pq):
    for pat, kind in EXPERIENCE_PATTERNS:
        m = re.search(pat + _EXP_TAIL, text)
        if not m:
            continue
        nums = [float(g) for g in m.groups()]
        if kind == "range":
            exp = {"op": "range", "min": min(nums), "max": max(nums)}
        else:
            exp = {"op": kind, "value": nums[0]}
        apply_experience(pq, exp)
        return _cut(text, m)
    return text


def _company_phrase(raw):
    co = raw.strip().removeprefix("the ").removeprefix("a ").removeprefix("an ").strip()
    return re.sub(r"\s+(?:companies|company|firms|firm|startups|organisations|organizations)$", "", co).strip()


def _set_company(pq, vocab, phrase, status, strong):
    """Accept phrase as a company. Strong cues ('worked at') accept it even if unseen in the data."""
    if vocab.company_exists(phrase):
        pq.company = _title(phrase)
    else:
        fixed = vocab.correct_company(phrase)
        if fixed:
            pq.company, pq.company_typed = _title(fixed), _title(phrase)
        elif strong:
            pq.company = _title(phrase)
        else:
            return False
    pq.company_status = status
    return True


def parse_query(query: str, vocab: Vocab) -> ParsedQuery:
    pq = ParsedQuery()
    text = " " + re.sub(r"\s+", " ", query.lower()).strip().rstrip(".!?") + " "
    text = re.sub(rf"\b({'|'.join(NUMBER_WORDS)})\b(?= ?\+? ?{_YRS})", lambda m: NUMBER_WORDS[m.group(1)], text)

    # --- experience
    text = _parse_experience(text, pq)

    # --- explicit name ("candidates named Rishabh Singh")
    m = _NAME_CUE_RE.search(text)
    if m and m.group(1).strip() and m.group(1).strip() not in FILLER:
        raw = m.group(1).strip()
        pq.name, pq.name_tokens = _title(raw), raw.split()
        text = _cut(text, m)

    # --- company ("worked at X", "current employees at X", "formerly at X", weak: "at X")
    for m in _COMPANY_CUE_RE.finditer(text):
        kind = next(k for k in ("current", "former", "any", "weak") if m.group(k))
        phrase = _company_phrase(m.group("co"))
        if not phrase or phrase in FILLER or re.match(r"(?:least|most)\b", phrase):
            continue
        if phrase in DOMAIN_QUERY_WORDS or phrase.rstrip("s") in DOMAIN_QUERY_WORDS:
            continue  # "worked at fintech companies" is a domain, handled below
        if kind == "weak":
            place = CITY_ALIASES.get(phrase, phrase)
            if COUNTRY_ALIASES.get(phrase, phrase) in vocab.countries or vocab.location_exists(place):
                continue
        if _set_company(pq, vocab, phrase, "any" if kind in ("any", "weak") else kind, strong=kind != "weak"):
            text = _cut(text, m)
            break

    # --- seniority
    m = _SENIORITY_RE.search(text)
    if m:
        key = m.group(0)
        pq.seniority = SENIORITY.get(key) or SENIORITY.get(key[:-1]) or SENIORITY.get(key[:-2])
        text = _cut(text, m)
        if pq.seniority in ("Entry", "Intern") and pq.experience is None:
            apply_experience(pq, {"op": "max", "value": 2})

    # --- domain ("with fintech experience", "who worked in fintech companies")
    m = _DOMAIN_RE.search(text)
    if m:
        key = m.group(0)
        key = key if key in DOMAIN_QUERY_WORDS else key.rstrip("s")
        pq.domain = DOMAIN_QUERY_WORDS.get(key)
        if pq.domain:
            pq.domain_terms = DOMAINS[pq.domain]
            text = _cut(text, m)

    # --- location: phrases after in/based in/located in/from, then any country mention
    for m in re.finditer(r"(?:based in|located in|living in|\bin|\bfrom|\bnear)\s+([a-z .'-]+?)(?= with | who | having | and |,|$| $)", text):
        place = m.group(1).strip().removeprefix("the ")
        place_c = COUNTRY_ALIASES.get(place, place)
        if place_c in vocab.countries and not pq.country:
            pq.country = _title(place_c)
            text = _cut(text, m)
            break
        place_l = CITY_ALIASES.get(place, place)
        if place and place not in FILLER and len(place) > 2 and vocab.location_exists(place_l) and not pq.location:
            pq.location = _title(place_l)
            text = _cut(text, m)
            break
    if not pq.country:
        for name in sorted(vocab.countries | set(COUNTRY_ALIASES), key=len, reverse=True):
            if len(name) < 4 and name not in ("usa", "uk", "uae"):
                continue
            m = re.search(rf"(?<![a-z]){re.escape(name)}(?![a-z])", text)
            if m:
                pq.country = _title(COUNTRY_ALIASES.get(name, name))
                text = _cut(text, m)
                break

    # --- stacks
    m = re.search(r"(?<![a-z])(mern|mean|mevn|lamp)(?: stack)?(?![a-z])", text)
    if m:
        pq.stack = m.group(1)
        pq.stack_skills = [{"name": sname, "aliases": SKILLS[sname]} for sname in STACKS[pq.stack]]
        text = _cut(text, m)
        if not any(r.search(text) for _, r, _ in _ROLE_RES):
            pq.role, pq.role_terms = "Full Stack Developer", ROLES["Full Stack Developer"][1] + GENERIC_DEV_TERMS

    # --- known role
    for name, rx, terms in _ROLE_RES:
        m = rx.search(text)
        if m and not pq.role:
            pq.role, pq.role_terms = name, list(terms)
            text = _cut(text, m)
            break

    # --- known skills (React Native before React, etc. handled by alias length ordering inside each regex)
    for name, rx, aliases in sorted(_SKILL_RES, key=lambda x: -max(len(a) for a in x[2])):
        m = rx.search(text)
        if m and name not in [s["name"] for s in pq.skills + pq.stack_skills]:
            pq.skills.append({"name": name, "aliases": aliases})
            text = _cut(text, m)

    # --- leftovers: generic developer role, name / company / title phrase, data-driven skill phrases, keywords
    def raw_tokens(s):
        return [w for w in (t.strip(".'") for t in re.findall(r"[a-z0-9.+#/&'-]+", s)) if w and w not in FILLER]

    all_words = [_singular(w) for w in raw_tokens(text)]
    if not pq.role:
        dev = [w for w in all_words if w in GENERIC_DEV_TERMS]
        others = [w for w in all_words if w not in GENERIC_DEV_TERMS]
        if dev and not others:
            pq.role, pq.role_terms = "Developer / Engineer", list(GENERIC_DEV_TERMS)

    raw_segments = [seg for seg in (raw_tokens(s) for s in re.split(r",|\b(?:with|who|having|and|in|at|that|for)\b", text))
                    if seg]
    segments = [[_singular(w) for w in seg] for seg in raw_segments]
    # A leading phrase with no recognised role is a person's name, a company or a job title,
    # whichever the data supports best (e.g. "Rishabh Singh", "Mahindra Bank", "yacht captains").
    if not pq.role and segments:
        raw, phrase = " ".join(raw_segments.pop(0)), " ".join(segments.pop(0))
        kind = _classify_phrase(raw, phrase, pq, vocab)
        if kind == "name":
            pq.name, pq.name_tokens = _title(raw), raw.split()
        elif kind == "company":
            _set_company(pq, vocab, raw, "any", strong=True)
        else:
            pq.role, pq.role_terms = _title(phrase), [phrase]
    words = [w for seg in segments for w in seg if w not in GENERIC_DEV_TERMS]

    # leftovers next to a known role: match against skills found in the data, else keywords
    i = 0
    while i < len(words):
        for n in (3, 2, 1):
            gram = " ".join(words[i:i + n])
            if len(words[i:i + n]) == n and gram in vocab.skills and len(gram) > 1:
                pq.skills.append({"name": _title(gram), "aliases": [gram]})
                i += n
                break
        else:
            if len(words[i]) > 1:
                pq.keywords.append(words[i])
            i += 1
    return pq


def _classify_phrase(raw, phrase, pq, vocab):
    """'name', 'company' or 'title' for a free-text phrase, based on where it occurs in the data."""
    looks_like_name = not pq.name and re.fullmatch(r"[a-z][a-z.'-]*(?: [a-z][a-z.'-]*){0,3}", raw) is not None
    counts = {
        "name": vocab.count("name", raw) if looks_like_name else 0,
        "company": vocab.count("company", raw) if not pq.company else 0,
        "title": vocab.count("title", phrase),
    }
    best = max(counts, key=lambda k: counts[k])  # ties keep dict order: name, company, title
    if counts[best] > 0:
        return best
    if not pq.company and (vocab.correct_company(raw) or COMPANY_HINTS & set(raw.split())):
        return "company"
    return "title"


def as_dict(pq: ParsedQuery):
    return asdict(pq)
