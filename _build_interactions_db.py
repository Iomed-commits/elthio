# -*- coding: utf-8 -*-
"""One-shot generator for interactions_db.json (75 rows). Run: python _build_interactions_db.py"""
import json
from pathlib import Path

def row(
    id_,
    title,
    severity,
    med_keywords,
    supp_keywords,
    detail,
    instruction,
    source,
    monitor=None,
    pair_type="drug_supplement",
):
    r = {
        "id": id_,
        "title": title,
        "severity": severity,
        "med_keywords": med_keywords,
        "supp_keywords": supp_keywords,
        "detail": detail,
        "instruction": instruction,
        "source": source,
    }
    if monitor:
        r["monitor"] = monitor
    if pair_type != "drug_supplement":
        r["pair_type"] = pair_type
    return r

STATIN = [
    "statin", "atorvastatin", "lipitor", "simvastatin", "zocor", "rosuvastatin",
    "crestor", "pravastatin", "lovastatin", "fluvastatin", "pitavastatin",
]
SSRI = [
    "ssri", "sertraline", "zoloft", "fluoxetine", "prozac", "escitalopram",
    "lexapro", "citalopram", "celexa", "paroxetine", "paxil", "fluvoxamine",
    "vortioxetine", "trintellix", "vilazodone", "viibryd",
]
SNRI = [
    "snri", "venlafaxine", "effexor", "duloxetine", "cymbalta",
    "desvenlafaxine", "pristiq", "levomilnacipran", "fetzima",
]
AD_EXTRA = [
    "bupropion", "wellbutrin", "zyban", "mirtazapine", "remeron",
    "trazodone", "nefazodone",
]
ACE = [
    "ace inhibitor", "lisinopril", "enalapril", "ramipril", "benazepril",
    "captopril", "quinapril", "perindopril",
]
BB = [
    "beta blocker", "metoprolol", "atenolol", "propranolol", "carvedilol",
    "bisoprolol", "nebivolol",
]
CCB = [
    "calcium channel blocker", "amlodipine", "norvasc", "diltiazem", "verapamil",
    "nifedipine", "felodipine",
]
PPI = ["ppi", "omeprazole", "prilosec", "esomeprazole", "nexium", "pantoprazole", "lansoprazole", "rabeprazole"]
H2 = ["h2 blocker", "famotidine", "pepcid", "ranitidine", "cimetidine"]
FLUORO = ["fluoroquinolone", "ciprofloxacin", "cipro", "levofloxacin", "moxifloxacin", "ofloxacin"]
TETRA = ["tetracycline", "doxycycline", "minocycline"]
DOAC = ["apixaban", "eliquis", "rivaroxaban", "xarelto", "dabigatran", "pradaxa", "edoxaban", "savaysa"]
BP_MED = ACE + BB + CCB + ["losartan", "valsartan", "irbesartan", "olmesartan", "hydrochlorothiazide", "hctz", "chlorthalidone"]
DIAB_MED = [
    "metformin", "glucophage", "glipizide", "glyburide", "glimepiride",
    "insulin", "sitagliptin", "januvia", "empagliflozin", "jardiance",
    "dapagliflozin", "farxiga", "canagliflozin", "invokana",
    "liraglutide", "ozempic", "semaglutide", "dulaglutide", "trulicity",
]
BENZO = [
    "benzodiazepine", "lorazepam", "ativan", "alprazolam", "xanax",
    "diazepam", "valium", "clonazepam", "klonopin", "temazepam",
    "oxazepam", "gabapentin", "neurontin", "pregabalin", "lyrica",
    "zolpidem", "ambien",
]
IMMUNO = ["cyclosporine", "tacrolimus", "prograf", "mycophenolate", "azathioprine"]
MAOI = [
    "maoi", "phenelzine", "nardil", "tranylcypromine", "parnate",
    "isocarboxazid", "marplan", "selegiline", "emsam",
]
LITHIUM = ["lithium", "lithobid", "eskalith", "lithium carbonate", "lithium citrate"]
DIGOXIN = ["digoxin", "lanoxin", "digitalis"]
PHENYTOIN = ["phenytoin", "dilantin", "fosphenytoin", "cerebyx"]
STEROID = [
    "prednisone", "prednisolone", "dexamethasone", "methylprednisolone",
    "medrol", "cortisone", "hydrocortisone", "budesonide", "corticosteroid",
    "steroid",
]
CLOPI = ["clopidogrel", "plavix"]
TAMOX = ["tamoxifen", "nolvadex", "soltamox"]
METHO = ["methotrexate", "rheumatrex", "trexall", "otrexup"]
HIV_MED = [
    "hiv medication", "antiretroviral", "atripla", "efavirenz", "ritonavir",
    "lopinavir", "darunavir", "atazanavir", "elvitegravir", "dolutegravir",
    "biktarvy", "genvoya", "stribild",
]
ADHD_MED = [
    "adderall", "amphetamine", "methylphenidate", "ritalin", "concerta",
    "vyvanse", "lisdexamfetamine", "dextroamphetamine", "dexedrine",
    "strattera", "atomoxetine",
]
ANTIPSYCH = [
    "antipsychotic", "quetiapine", "seroquel", "olanzapine", "zyprexa",
    "risperidone", "risperdal", "aripiprazole", "abilify", "haloperidol",
    "haldol", "clozapine", "clozaril", "ziprasidone", "geodon",
    "lurasidone", "latuda",
]
SPIRO = ["spironolactone", "aldactone", "eplerenone", "inspra"]
CONTRA = [
    "oral contraceptive", "birth control", "the pill", "ethinyl estradiol",
    "drospirenone", "levonorgestrel", "norethindrone", "norgestimate",
    "yaz", "yasmin", "ortho tri-cyclen", "loestrin", "nuvaring",
    "etonogestrel", "estrogen", "estradiol", "hormone replacement", "premarin",
]
DIURETIC = [
    "furosemide", "lasix", "bumetanide", "torsemide", "ethacrynic acid",
    "hydrochlorothiazide", "hctz", "chlorthalidone", "indapamide",
    "metolazone", "thiazide", "loop diuretic",
]
ASPIRIN = [
    "aspirin", "acetylsalicylic acid", "asa", "ecotrin", "bayer aspirin",
    "low-dose aspirin", "baby aspirin",
]

ROWS = []

# GROUP 1 — Anticoagulants
W = ["warfarin", "coumadin", "jantoven"]
ROWS += [
    row("warfarin-vitamin-k", "Warfarin ↔ vitamin K", "critical", W,
        ["vitamin k", "vitamin k1", "vitamin k2", "mk-7", "mk-4", "menaquinone",
         "phylloquinone", "k2", "k1", "greens powder", "kale powder",
         "spinach powder", "chlorophyll supplement"],
        "Vitamin K opposes warfarin's anticoagulant effect and can shift INR unpredictably.",
        "Keep vitamin K intake consistent; do not start or stop K supplements without prescriber guidance and INR monitoring.",
        "FDA warfarin label / MedlinePlus", "INR"),
    row("warfarin-omega3-high", "Warfarin ↔ high-dose omega-3", "high", W,
        ["fish oil", "omega-3", "omega 3", "epa", "dha", "cod liver oil"],
        "High-dose omega-3 fatty acids may add to antiplatelet effects and increase bleeding risk with warfarin.",
        "Discuss fish oil dose with your clinician; report bruising or bleeding; INR may need monitoring.",
        "NIH ODS omega-3 / MedlinePlus warfarin", "INR, bleeding signs"),
    row("warfarin-vitamin-e-high", "Warfarin ↔ vitamin E (>400 IU/day)", "high", W,
        ["vitamin e", "tocopherol", "tocotrienol"],
        "Vitamin E at higher doses may increase bleeding risk when combined with warfarin.",
        "Avoid high-dose vitamin E unless your care team approves; monitor for bruising or bleeding.",
        "NIH ODS vitamin E / MedlinePlus"),
    row("warfarin-coq10", "Warfarin ↔ CoQ10", "informational", W,
        ["coq10", "coenzyme q10", "ubiquinol", "ubiquinone"],
        "Some reports suggest CoQ10 may reduce warfarin effect but evidence is inconsistent and weak.",
        "If you use CoQ10, inform your prescriber. INR monitoring when starting or stopping is prudent.",
        "MedlinePlus / FDA label interactions — evidence mixed"),
    row("warfarin-garlic", "Warfarin ↔ garlic supplement", "moderate", W,
        ["garlic", "allicin", "aged garlic"],
        "Garlic supplements may increase bleeding risk with anticoagulants.",
        "Discuss garlic supplements with your pharmacist; watch for unusual bruising or bleeding.",
        "NIH ODS garlic / MedlinePlus"),
    row("warfarin-ginkgo", "Warfarin ↔ ginkgo biloba", "high", W, ["ginkgo", "ginkgo biloba", "egb"],
        "Ginkgo may inhibit platelet function and increase bleeding risk with warfarin.",
        "Avoid combining unless your clinician directs otherwise; report bleeding promptly.",
        "MedlinePlus ginkgo / FDA safety communications"),
    row("warfarin-turmeric", "Warfarin ↔ turmeric/curcumin", "moderate", W,
        ["turmeric", "curcumin", "curcuma"],
        "Turmeric/curcumin may have antiplatelet activity and affect bleeding risk with warfarin.",
        "Discuss turmeric supplements with your care team; monitor INR if you start or stop.",
        "NIH NCCIH turmeric / MedlinePlus"),
    row("warfarin-st-johns-wort", "Warfarin ↔ St. John's Wort", "critical", W,
        ["st. john's wort", "st johns wort", "hypericum"],
        "St. John's Wort induces drug-metabolizing enzymes and can markedly lower warfarin levels.",
        "Avoid St. John's Wort with warfarin unless explicitly approved with INR monitoring.",
        "FDA drug interactions / MedlinePlus"),
    row("warfarin-vitamin-c-high", "Warfarin ↔ high-dose vitamin C", "moderate", W,
        ["vitamin c", "ascorbic acid", "ester-c"],
        "Very high doses of vitamin C have been associated with altered warfarin response in some reports.",
        "Discuss megadose vitamin C with your prescriber; maintain consistent intake if approved.",
        "MedlinePlus / clinical references"),
    row("apixaban-omega3", "Apixaban ↔ omega-3", "high", ["apixaban", "eliquis"],
        ["fish oil", "omega-3", "omega 3", "epa", "dha"],
        "Omega-3 supplements may add to bleeding risk with apixaban.",
        "Discuss dose with your clinician; seek care for major bleeding or prolonged bruising.",
        "FDA apixaban label / NIH ODS"),
    row("apixaban-vitamin-e", "Apixaban ↔ vitamin E", "moderate", ["apixaban", "eliquis"],
        ["vitamin e", "tocopherol"],
        "Higher-dose vitamin E may increase bleeding risk with anticoagulants including apixaban.",
        "Use vitamin E doses only as directed by your care team; report bleeding symptoms.",
        "NIH ODS vitamin E"),
    row("rivaroxaban-omega3", "Rivaroxaban ↔ omega-3", "high", ["rivaroxaban", "xarelto"],
        ["fish oil", "omega-3", "omega 3", "epa", "dha"],
        "Omega-3 may increase bleeding risk when taken with rivaroxaban.",
        "Discuss fish oil with your prescriber; report signs of bleeding.",
        "FDA rivaroxaban label / NIH ODS"),
    row("dabigatran-omega3", "Dabigatran ↔ omega-3", "high", ["dabigatran", "pradaxa"],
        ["fish oil", "omega-3", "omega 3", "epa", "dha"],
        "Omega-3 may add to bleeding risk with dabigatran.",
        "Discuss supplement use with your clinician before starting high-dose fish oil.",
        "FDA dabigatran label / NIH ODS"),
]

# GROUP 2 — Statins
ROWS += [
    row("statin-coq10", "Statin ↔ CoQ10", "informational", STATIN,
        ["coq10", "coenzyme q10", "ubiquinol"],
        "Statins lower CoQ10 synthesis; supplementation is commonly discussed for muscle symptoms.",
        "Discuss whether CoQ10 fits your plan; report unexplained muscle pain to your clinician.",
        "NIH ODS CoQ10 / MedlinePlus statins"),
    row("statin-grapefruit", "Simvastatin/lovastatin ↔ grapefruit", "high",
        ["simvastatin", "zocor", "lovastatin", "mevacor", "statin"],
        ["grapefruit", "grapefruit juice"],
        "Grapefruit inhibits CYP3A4 and can raise blood levels of simvastatin and lovastatin, increasing myopathy risk.",
        "Avoid grapefruit and grapefruit juice with these statins unless your prescriber advises otherwise.",
        "FDA statin labels / MedlinePlus"),
    row("statin-niacin-high", "Statin ↔ high-dose niacin", "high", STATIN,
        ["niacin", "nicotinic acid", "niaspan", "inositol hexanicotinate"],
        "Combined statin and high-dose niacin may increase risk of muscle injury (myopathy/rhabdomyolysis).",
        "Do not add high-dose niacin to a statin without medical supervision and monitoring.",
        "FDA label / MedlinePlus"),
    row("statin-red-yeast-rice", "Statin ↔ red yeast rice", "critical", STATIN,
        ["red yeast rice", "red yeast", "monacolin"],
        "Red yeast rice contains monacolin K (a lovastatin-like compound) and can double statin exposure.",
        "Do not combine red yeast rice with prescription statins unless directed by your prescriber.",
        "FDA / NIH NCCIH red yeast rice", "CK, muscle pain"),
]

# GROUP 3 — Thyroid
LT4 = [
    "levothyroxine", "synthroid", "levoxyl", "tirosint", "unithroid",
    "thyroid medication", "hypothyroid", "nature-throid", "np thyroid",
    "wp thyroid", "armour thyroid", "desiccated thyroid", "liothyronine",
    "cytomel", "t3", "t4",
]
ROWS += [
    row("levothyroxine-calcium", "Levothyroxine ↔ calcium", "critical", LT4,
        ["calcium", "calcium carbonate", "calcium citrate", "tums", "antacid"],
        "Calcium binds levothyroxine in the gut and reduces absorption.",
        "Separate levothyroxine and calcium by at least 4 hours.",
        "FDA levothyroxine label / MedlinePlus", "TSH"),
    row("levothyroxine-iron", "Levothyroxine ↔ iron", "critical", LT4,
        ["iron", "ferrous sulfate", "ferrous gluconate", "ferrous fumarate"],
        "Iron reduces levothyroxine absorption when taken together.",
        "Take levothyroxine at least 4 hours apart from iron supplements.",
        "FDA label / MedlinePlus", "TSH"),
    row("levothyroxine-magnesium", "Levothyroxine ↔ magnesium", "critical", LT4,
        ["magnesium", "magnesium oxide", "magnesium citrate", "magnesium glycinate"],
        "Magnesium can reduce levothyroxine absorption.",
        "Separate doses by at least 4 hours.",
        "FDA label / MedlinePlus", "TSH"),
    row("levothyroxine-zinc", "Levothyroxine ↔ zinc", "moderate", LT4, ["zinc", "zinc gluconate", "zinc picolinate"],
        "Zinc may reduce levothyroxine absorption.",
        "Take levothyroxine at least 4 hours apart from zinc.",
        "FDA label / MedlinePlus", "TSH"),
    row("levothyroxine-fiber", "Levothyroxine ↔ fiber/psyllium", "moderate", LT4,
        ["fiber", "psyllium", "metamucil", "methylcellulose"],
        "Fiber supplements can reduce levothyroxine absorption.",
        "Separate by at least 2 hours from levothyroxine.",
        "FDA label / MedlinePlus"),
    row("levothyroxine-soy", "Levothyroxine ↔ soy", "moderate", LT4,
        ["soy", "soy protein", "soy isoflavone", "genistein"],
        "Soy products may reduce levothyroxine absorption in some patients.",
        "Keep soy intake consistent and separate large soy doses from thyroid medication when possible.",
        "MedlinePlus / FDA label"),
    row("levothyroxine-coffee", "Levothyroxine ↔ coffee", "moderate", LT4,
        ["coffee", "caffeine beverage"],
        "Coffee taken with levothyroxine can reduce absorption.",
        "Take levothyroxine with water; wait 30–60 minutes before coffee.",
        "Clinical studies cited in thyroid drug labeling"),
    row("levothyroxine-biotin-high", "Levothyroxine ↔ high-dose biotin", "moderate", LT4,
        ["biotin", "high dose biotin"],
        "High-dose biotin can interfere with some thyroid blood tests (false results).",
        "Tell your lab and clinician if you take biotin; stop high-dose biotin before labs if directed.",
        "FDA biotin lab interference alert", "TSH, free T4 assays"),
]

# GROUP 4 — Antidepressants
AD = SSRI + SNRI + AD_EXTRA
ROWS += [
    row("ssri-st-johns-wort", "SSRI/SNRI ↔ St. John's Wort", "critical", AD,
        ["st. john's wort", "st johns wort", "hypericum"],
        "Combining serotonergic antidepressants with St. John's Wort increases serotonin syndrome risk.",
        "Do not combine without medical supervision; seek care for agitation, fever, or rapid heartbeat.",
        "FDA / MedlinePlus serotonin syndrome"),
    row("ssri-5htp", "SSRI/SNRI ↔ 5-HTP", "critical", AD, ["5-htp", "5 htp", "oxitriptan"],
        "5-HTP adds serotonergic activity and can increase serotonin syndrome risk with SSRIs/SNRIs.",
        "Avoid combining unless explicitly directed by a psychiatrist or prescriber.",
        "MedlinePlus / FDA safety communications"),
    row("ssri-same", "SSRI/SNRI ↔ SAMe", "high", AD, ["same", "s-adenosylmethionine", "sam-e"],
        "SAMe may increase serotonergic activity when combined with antidepressants.",
        "Discuss SAMe with your prescriber before use; report anxiety, tremor, or insomnia.",
        "MedlinePlus SAMe"),
    row("ssri-tryptophan", "SSRI/SNRI ↔ tryptophan", "high", AD, ["tryptophan", "l-tryptophan"],
        "Tryptophan increases serotonin precursor load and may raise serotonin syndrome risk with SSRIs.",
        "Avoid tryptophan supplements with SSRIs unless your clinician approves.",
        "MedlinePlus"),
    row("ssri-omega3", "SSRI/SNRI ↔ omega-3", "informational", AD,
        ["fish oil", "omega-3", "omega 3", "epa", "dha"],
        "Omega-3 fatty acids are often studied as adjuncts to antidepressants with generally favorable safety profiles.",
        "Continue prescribed antidepressants; discuss omega-3 dose with your care team.",
        "NIH ODS omega-3"),
    row("ssri-melatonin", "SSRI/SNRI ↔ melatonin", "moderate", AD, ["melatonin"],
        "Melatonin may add to sedation or sleepiness with some antidepressants.",
        "Use lowest effective melatonin dose; avoid driving if overly sedated.",
        "MedlinePlus melatonin"),
]

# GROUP 5 — Diabetes
ROWS += [
    row("metformin-b12", "Metformin ↔ vitamin B12", "high", ["metformin", "glucophage"],
        ["vitamin b12", "b12", "cobalamin", "methylcobalamin", "cyanocobalamin"],
        "Long-term metformin use is associated with lower vitamin B12 levels.",
        "Discuss B12 monitoring or supplementation with your clinician.",
        "NIH ODS / MedlinePlus metformin", "B12 level"),
    row("metformin-chromium", "Metformin ↔ chromium", "moderate", ["metformin", "glucophage"],
        ["chromium", "chromium picolinate"],
        "Chromium may affect glucose; combined use can increase hypoglycemia risk.",
        "Monitor blood sugar if adding chromium; report dizziness or sweating.",
        "NIH ODS chromium", "blood glucose"),
    row("metformin-berberine", "Metformin ↔ berberine", "high", ["metformin", "glucophage"], ["berberine"],
        "Berberine and metformin both lower blood glucose and may have additive effects.",
        "Do not combine without medical supervision; monitor glucose closely.",
        "NIH NCCIH / clinical literature", "blood glucose"),
    row("metformin-ala", "Metformin ↔ alpha-lipoic acid", "moderate", ["metformin", "glucophage"],
        ["alpha lipoic acid", "alpha-lipoic acid", "ala", "thioctic acid"],
        "Alpha-lipoic acid may lower blood glucose and add to metformin's effect.",
        "Monitor blood sugar when starting ALA; discuss dose with your clinician.",
        "MedlinePlus / NIH ODS"),
    row("diabetes-magnesium", "Diabetes medication ↔ magnesium", "informational", DIAB_MED,
        ["magnesium", "magnesium glycinate", "magnesium citrate"],
        "Magnesium is involved in glucose metabolism; supplementation may affect insulin sensitivity.",
        "Monitor glucose if you add magnesium; keep your diabetes team informed.",
        "NIH ODS magnesium", "blood glucose"),
    row("sulfonylurea-chromium", "Sulfonylurea ↔ chromium", "high",
        ["glipizide", "glyburide", "glimepiride"],
        ["chromium", "chromium picolinate"],
        "Chromium may enhance insulin action and increase hypoglycemia risk with sulfonylureas.",
        "Monitor blood sugar closely if using chromium; know hypoglycemia symptoms.",
        "NIH ODS chromium", "blood glucose"),
]

# GROUP 6 — Blood pressure
ROWS += [
    row("ace-potassium", "ACE inhibitor ↔ potassium", "high", ACE,
        ["potassium", "potassium chloride", "potassium citrate", "salt substitute"],
        "ACE inhibitors reduce potassium loss and supplementation can cause hyperkalemia.",
        "Avoid potassium supplements or salt substitutes unless prescribed; check potassium labs.",
        "FDA ACE inhibitor labels / MedlinePlus", "serum potassium"),
    row("ace-magnesium", "ACE inhibitor ↔ magnesium", "moderate", ACE,
        ["magnesium", "magnesium supplement"],
        "Magnesium may add to blood pressure lowering with ACE inhibitors.",
        "Monitor blood pressure when starting magnesium; report dizziness.",
        "MedlinePlus"),
    row("bb-coq10", "Beta blocker ↔ CoQ10", "informational", BB,
        ["coq10", "coenzyme q10", "ubiquinol"],
        "CoQ10 is sometimes used alongside heart medications; evidence for harm with beta blockers is limited.",
        "Discuss supplements with your cardiologist; do not stop beta blockers abruptly.",
        "NIH ODS CoQ10"),
    row("ccb-grapefruit", "Calcium channel blocker ↔ grapefruit", "high", CCB,
        ["grapefruit", "grapefruit juice"],
        "Grapefruit inhibits intestinal metabolism and can raise levels of many calcium channel blockers.",
        "Avoid grapefruit with felodipine/nifedipine-like agents unless your prescriber approves.",
        "FDA CCB labels / MedlinePlus"),
    row("ccb-calcium-supplement", "CCB ↔ calcium supplements", "moderate", CCB,
        ["calcium", "calcium carbonate", "calcium citrate"],
        "High calcium intake does not replace CCB therapy and very high doses may affect mineral balance.",
        "Take calcium as directed; do not use calcium to replace blood pressure medication.",
        "MedlinePlus"),
    row("bp-licorice", "Blood pressure medication ↔ licorice root", "high", BP_MED,
        ["licorice", "licorice root", "glycyrrhizin", "deglycyrrhizinated licorice"],
        "Licorice can raise blood pressure and oppose antihypertensive therapy.",
        "Avoid licorice supplements with hypertension unless your clinician approves.",
        "NIH NCCIH licorice / MedlinePlus"),
    row("bp-caffeine-high", "Blood pressure medication ↔ high-dose caffeine", "moderate", BP_MED,
        ["caffeine", "energy drink", "guarana", "high dose coffee"],
        "High caffeine intake can transiently raise blood pressure and blunt medication control.",
        "Limit large caffeine doses; monitor home blood pressure.",
        "MedlinePlus caffeine"),
]

# GROUP 7 — Acid reducers
ACID = PPI + H2
ROWS += [
    row("ppi-iron", "PPI ↔ iron", "moderate", ACID,
        ["iron", "ferrous sulfate", "ferrous gluconate"],
        "PPIs reduce stomach acid needed for optimal iron absorption.",
        "Separate iron from PPI when possible; discuss labs if on long-term PPI.",
        "MedlinePlus PPI / NIH ODS iron", "ferritin, CBC"),
    row("ppi-magnesium", "PPI ↔ magnesium", "high", ACID,
        ["magnesium", "magnesium oxide", "magnesium citrate"],
        "Long-term PPI use is associated with hypomagnesemia in some patients.",
        "Discuss magnesium monitoring with your clinician if on PPIs long term.",
        "FDA PPI labeling / MedlinePlus", "serum magnesium"),
    row("ppi-b12", "PPI ↔ vitamin B12", "moderate", ACID,
        ["vitamin b12", "b12", "cobalamin"],
        "Reduced acid can impair B12 absorption over time with PPI therapy.",
        "Consider B12 status monitoring with long-term PPI use.",
        "FDA PPI labeling / MedlinePlus", "B12 level"),
    row("ppi-calcium", "PPI ↔ calcium carbonate", "moderate", ACID,
        ["calcium carbonate", "calcium antacid", "tums"],
        "Calcium carbonate needs acid for absorption; PPIs may reduce its effectiveness.",
        "Consider calcium citrate with low acid states; separate timing from PPI if advised.",
        "NIH ODS calcium"),
    row("ppi-zinc", "PPI ↔ zinc", "moderate", ACID, ["zinc", "zinc gluconate"],
        "Low stomach acid may reduce zinc absorption during long-term acid suppression.",
        "Discuss zinc needs with your clinician if on chronic PPI therapy.",
        "MedlinePlus"),
]

# GROUP 8 — Antibiotics
ROWS += [
    row("fluoroquinolone-calcium", "Fluoroquinolone ↔ calcium", "high", FLUORO,
        ["calcium", "calcium carbonate", "calcium citrate", "antacid"],
        "Calcium chelates fluoroquinolones and reduces antibiotic absorption.",
        "Separate fluoroquinolone and calcium by at least 2 hours.",
        "FDA fluoroquinolone label / MedlinePlus"),
    row("fluoroquinolone-magnesium", "Fluoroquinolone ↔ magnesium", "high", FLUORO,
        ["magnesium", "magnesium oxide", "magnesium citrate"],
        "Magnesium reduces fluoroquinolone absorption.",
        "Take antibiotic 2 hours before or 6 hours after magnesium.",
        "FDA label / MedlinePlus"),
    row("fluoroquinolone-iron", "Fluoroquinolone ↔ iron", "high", FLUORO,
        ["iron", "ferrous sulfate", "ferrous gluconate"],
        "Iron binds fluoroquinolones and reduces absorption.",
        "Separate doses by at least 2 hours.",
        "FDA label / MedlinePlus"),
    row("fluoroquinolone-zinc", "Fluoroquinolone ↔ zinc", "high", FLUORO, ["zinc"],
        "Zinc can reduce fluoroquinolone absorption.",
        "Separate zinc and fluoroquinolone by several hours.",
        "FDA label / MedlinePlus"),
    row("tetracycline-calcium", "Tetracycline ↔ calcium", "high", TETRA,
        ["calcium", "calcium carbonate", "dairy", "milk", "yogurt", "cheese"],
        "Calcium and dairy reduce tetracycline absorption.",
        "Avoid calcium/dairy within 2 hours of tetracycline doses.",
        "FDA tetracycline label / MedlinePlus"),
    row("tetracycline-iron", "Tetracycline ↔ iron", "high", TETRA,
        ["iron", "ferrous sulfate"],
        "Iron reduces tetracycline absorption.",
        "Separate iron and tetracycline by at least 2 hours.",
        "FDA label / MedlinePlus"),
    row("tetracycline-dairy", "Tetracycline ↔ dairy", "high", TETRA,
        ["dairy", "milk", "calcium-rich food"],
        "Dairy calcium binds tetracycline and lowers antibiotic levels.",
        "Take tetracycline 1 hour before or 2 hours after dairy meals.",
        "FDA label / MedlinePlus"),
    row("antibiotic-probiotic", "Antibiotic ↔ probiotics", "moderate",
        ["antibiotic", "amoxicillin", "azithromycin", "doxycycline", "ciprofloxacin"] + FLUORO + TETRA,
        ["probiotic", "lactobacillus", "saccharomyces boulardii", "acidophilus"],
        "Antibiotics can kill probiotic bacteria if taken at the same time.",
        "Take probiotic at least 2 hours apart from antibiotic doses.",
        "MedlinePlus / clinical practice references"),
]

# GROUP 9 — Immunosuppressants
ROWS += [
    row("cyclosporine-st-johns-wort", "Cyclosporine ↔ St. John's Wort", "critical",
        ["cyclosporine", "neoral", "sandimmune"],
        ["st. john's wort", "st johns wort", "hypericum"],
        "St. John's Wort induces metabolism and can drastically lower cyclosporine levels.",
        "Avoid St. John's Wort with transplant medications unless transplant team approves.",
        "FDA transplant drug labels / MedlinePlus", "drug levels"),
    row("cyclosporine-grapefruit", "Cyclosporine ↔ grapefruit", "critical", ["cyclosporine"],
        ["grapefruit", "grapefruit juice"],
        "Grapefruit inhibits metabolism and can raise cyclosporine to toxic levels.",
        "Avoid grapefruit completely with cyclosporine unless transplant team directs otherwise.",
        "FDA label / MedlinePlus", "drug levels, kidney function"),
    row("tacrolimus-st-johns-wort", "Tacrolimus ↔ St. John's Wort", "critical",
        ["tacrolimus", "prograf", "envarsus"],
        ["st. john's wort", "st johns wort"],
        "St. John's Wort can lower tacrolimus concentrations and risk transplant rejection.",
        "Do not use St. John's Wort with tacrolimus.",
        "FDA label / MedlinePlus", "tacrolimus level"),
    row("immunosuppressant-echinacea", "Immunosuppressant ↔ echinacea", "high", IMMUNO,
        ["echinacea"],
        "Echinacea may stimulate immune activity and oppose immunosuppressive therapy.",
        "Avoid echinacea with transplant or autoimmune immunosuppression unless approved.",
        "NIH NCCIH echinacea / MedlinePlus"),
]

# GROUP 10 — Neurological / Parkinson's
LEVO = ["levodopa", "carbidopa", "sinemet", "rytary", "duopa"]
ROWS += [
    row("levodopa-iron", "Levodopa ↔ iron", "high", LEVO,
        ["iron", "ferrous sulfate", "multivitamin with iron"],
        "Iron chelates levodopa in the gut and reduces absorption.",
        "Separate levodopa and iron by at least 2 hours.",
        "MedlinePlus levodopa / FDA label"),
    row("levodopa-b6-high", "Levodopa ↔ high-dose vitamin B6", "high", LEVO,
        ["vitamin b6", "pyridoxine", "b6"],
        "High-dose vitamin B6 can accelerate peripheral metabolism of levodopa and reduce effect.",
        "Avoid high-dose B6 unless your neurologist prescribes it.",
        "MedlinePlus / FDA label", "Parkinson symptoms"),
    row("levodopa-protein", "Levodopa ↔ protein supplements", "high", LEVO,
        ["protein powder", "whey protein", "amino acid", "bcaa", "protein shake"],
        "Large protein loads compete for brain uptake of levodopa.",
        "Time protein supplements away from levodopa per your movement-disorder specialist.",
        "MedlinePlus / clinical guidelines"),
]

# GROUP 11 — Mineral interactions (supplement–supplement)
ROWS += [
    row("calcium-iron", "Calcium ↔ iron", "high",
        ["calcium", "calcium carbonate", "calcium citrate"],
        ["iron", "ferrous sulfate", "ferrous gluconate"],
        "Calcium inhibits iron absorption when taken together.",
        "Take iron and calcium at least 2 hours apart.",
        "NIH ODS iron / NIH ODS calcium", pair_type="supplement_supplement"),
    row("calcium-magnesium-high", "Calcium ↔ magnesium (high dose)", "informational",
        ["calcium", "calcium carbonate"],
        ["magnesium", "magnesium oxide", "magnesium citrate"],
        "At typical supplement doses calcium and magnesium compete minimally for absorption. Very high combined doses may reduce uptake of both.",
        "At standard doses this is not a significant concern. If taking high doses of both, split across meals.",
        "NIH ODS", pair_type="supplement_supplement"),
    row("zinc-copper", "Zinc ↔ copper", "high", ["zinc", "zinc gluconate", "zinc picolinate"],
        ["copper", "cupric oxide"],
        "Long-term high-dose zinc can deplete copper and cause deficiency.",
        "Discuss zinc dose and copper monitoring with your clinician for prolonged use.",
        "NIH ODS zinc / copper", "copper level", pair_type="supplement_supplement"),
    row("zinc-iron", "Zinc ↔ iron", "moderate", ["zinc"], ["iron", "ferrous sulfate"],
        "Zinc and iron compete for absorption when taken together.",
        "Separate zinc and iron by at least 2 hours.",
        "NIH ODS", pair_type="supplement_supplement"),
    row("iron-vitamin-c", "Iron ↔ vitamin C", "informational",
        ["iron", "ferrous sulfate", "ferrous gluconate"],
        ["vitamin c", "ascorbic acid"],
        "Vitamin C enhances non-heme iron absorption when taken together.",
        "Pair iron with vitamin C for absorption unless your clinician advises otherwise.",
        "NIH ODS iron", pair_type="supplement_supplement"),
]

# GROUP 12 — Sedatives / sleep
ROWS += [
    row("benzo-melatonin", "Benzodiazepine ↔ melatonin", "moderate", BENZO, ["melatonin"],
        "Melatonin may add to sedation with benzodiazepines.",
        "Use lowest doses; avoid alcohol; do not drive if impaired.",
        "MedlinePlus"),
    row("benzo-valerian", "Benzodiazepine ↔ valerian", "moderate", BENZO, ["valerian", "valeriana"],
        "Valerian may increase sedation with benzodiazepines.",
        "Avoid combining sedative herbs with benzodiazepines unless approved.",
        "NIH NCCIH valerian"),
    row("benzo-kava", "Benzodiazepine ↔ kava", "high", BENZO, ["kava", "kava kava", "piper methysticum"],
        "Kava adds sedation and carries liver toxicity risk, worsened with CNS depressants.",
        "Avoid kava with benzodiazepines.",
        "FDA kava advisory / MedlinePlus"),
    row("zolpidem-melatonin", "Zolpidem ↔ melatonin", "moderate",
        ["zolpidem", "ambien", "eszopiclone", "lunesta", "zaleplon"],
        ["melatonin"],
        "Melatonin may increase sedation with sedative-hypnotics.",
        "Use cautiously; avoid alcohol the same night.",
        "MedlinePlus"),
]

# GROUP 13 — Bisphosphonates
BIS = ["alendronate", "fosamax", "risedronate", "actonel", "ibandronate", "boniva", "zoledronic acid"]
ROWS += [
    row("alendronate-calcium", "Bisphosphonate ↔ calcium", "critical", BIS,
        ["calcium", "calcium carbonate", "calcium citrate", "antacid"],
        "Calcium and food substantially reduce bisphosphonate absorption.",
        "Take bisphosphonate on empty stomach with plain water; delay calcium per label instructions.",
        "FDA bisphosphonate labels / MedlinePlus"),
    row("alendronate-iron", "Bisphosphonate ↔ iron", "high", BIS,
        ["iron", "ferrous sulfate"],
        "Iron and minerals reduce bisphosphonate absorption.",
        "Do not take iron within several hours of oral bisphosphonate.",
        "FDA label / MedlinePlus"),
    row("alendronate-magnesium", "Bisphosphonate ↔ magnesium", "high", BIS,
        ["magnesium", "magnesium oxide"],
        "Magnesium reduces bisphosphonate absorption.",
        "Separate magnesium from oral bisphosphonate by several hours.",
        "FDA label / MedlinePlus"),
]

# GROUP 14 — Lithium
ROWS += [
    row("lithium-sodium-restriction", "Lithium ↔ low sodium / salt restriction", "critical",
        LITHIUM,
        ["low sodium diet", "sodium restriction", "salt substitute", "no-salt",
         "nosalt", "nu-salt", "potassium chloride salt"],
        "Sodium and lithium compete for kidney reabsorption. Low sodium intake causes lithium "
        "to accumulate to potentially toxic levels.",
        "Never start a low-sodium diet or use salt substitutes without telling your prescriber. "
        "Maintain consistent sodium intake. Report tremor, confusion, or nausea immediately.",
        "FDA lithium label / MedlinePlus", "lithium level, kidney function"),

    row("lithium-caffeine-high", "Lithium ↔ high-dose caffeine", "moderate",
        LITHIUM,
        ["caffeine", "energy drink", "guarana", "high dose coffee"],
        "Sudden changes in caffeine intake can shift lithium levels — caffeine increases "
        "kidney lithium clearance.",
        "Keep caffeine intake consistent. Do not suddenly start or stop high caffeine use "
        "while on lithium.",
        "MedlinePlus / lithium pharmacokinetics literature", "lithium level"),

    row("lithium-magnesium", "Lithium ↔ magnesium", "moderate",
        LITHIUM,
        ["magnesium", "magnesium citrate", "magnesium glycinate", "magnesium oxide"],
        "Magnesium and lithium share some renal handling pathways. High-dose magnesium "
        "may affect lithium clearance in some patients.",
        "Discuss magnesium supplementation with your prescriber if you take lithium. "
        "Keep your psychiatry team informed of all supplements.",
        "MedlinePlus / clinical case literature", "lithium level"),
]

# GROUP 15 — MAOIs
ROWS += [
    row("maoi-5htp", "MAOI ↔ 5-HTP", "critical", MAOI,
        ["5-htp", "5 htp", "hydroxytryptophan", "oxitriptan"],
        "5-HTP combined with MAOIs can cause severe serotonin syndrome — a potentially "
        "life-threatening condition with fever, seizures, and cardiovascular instability.",
        "Never combine 5-HTP with MAOIs. Seek emergency care for agitation, fever, "
        "rigid muscles, or rapid heart rate.",
        "FDA / MedlinePlus serotonin syndrome"),

    row("maoi-tryptophan", "MAOI ↔ tryptophan", "critical", MAOI,
        ["tryptophan", "l-tryptophan"],
        "Tryptophan with MAOIs can precipitate serotonin syndrome.",
        "Do not combine tryptophan supplements with MAOIs under any circumstances.",
        "FDA / MedlinePlus"),

    row("maoi-tyrosine", "MAOI ↔ tyrosine", "critical", MAOI,
        ["tyrosine", "l-tyrosine", "phenylalanine", "l-phenylalanine"],
        "Tyrosine is a precursor to tyramine. MAOIs block tyramine breakdown and "
        "combined with tyrosine supplements can trigger hypertensive crisis.",
        "Avoid tyrosine and phenylalanine supplements with MAOIs. "
        "Report sudden severe headache immediately — this is a medical emergency.",
        "FDA MAOI labels / MedlinePlus", "blood pressure"),

    row("maoi-ginseng", "MAOI ↔ ginseng", "high", MAOI,
        ["ginseng", "panax ginseng", "korean ginseng", "american ginseng"],
        "Ginseng may have serotonergic and stimulant properties that interact with MAOIs.",
        "Avoid ginseng supplements with MAOIs unless your psychiatrist approves.",
        "NIH NCCIH ginseng / MedlinePlus"),
]

# GROUP 16 — Digoxin
ROWS += [
    row("digoxin-hawthorn", "Digoxin ↔ hawthorn", "high", DIGOXIN,
        ["hawthorn", "crataegus", "hawthorn berry", "hawthorn extract"],
        "Hawthorn has cardiac glycoside-like activity and can add to digoxin's effects, "
        "potentially causing toxicity.",
        "Do not combine hawthorn with digoxin without cardiology approval. "
        "Report nausea, visual disturbance, or irregular heartbeat immediately.",
        "NIH NCCIH hawthorn / MedlinePlus", "digoxin level, heart rate"),

    row("digoxin-magnesium", "Digoxin ↔ magnesium", "high", DIGOXIN,
        ["magnesium", "magnesium oxide", "magnesium citrate", "magnesium glycinate"],
        "Low magnesium increases digoxin toxicity risk. High-dose magnesium supplements "
        "can affect cardiac conduction in digoxin-treated patients.",
        "Maintain adequate magnesium but avoid high-dose supplementation without "
        "cardiology guidance. Report palpitations or visual changes.",
        "FDA digoxin label / MedlinePlus", "serum magnesium, digoxin level"),

    row("digoxin-st-johns-wort", "Digoxin ↔ St. John's Wort", "critical", DIGOXIN,
        ["st. john's wort", "st johns wort", "hypericum"],
        "St. John's Wort induces P-glycoprotein and CYP enzymes, significantly reducing "
        "digoxin levels and risking loss of cardiac control.",
        "Do not use St. John's Wort with digoxin.",
        "FDA drug interaction labeling / MedlinePlus", "digoxin level"),
]

# GROUP 17 — Phenytoin / anti-epileptics
ROWS += [
    row("phenytoin-folic-acid", "Phenytoin ↔ folic acid", "high", PHENYTOIN,
        ["folic acid", "folate", "methylfolate", "5-mthf", "vitamin b9"],
        "Phenytoin lowers folate levels. However high-dose folic acid can also lower "
        "phenytoin levels and increase seizure risk.",
        "Take only the folic acid dose your neurologist recommends. "
        "Do not self-supplement with high-dose folate on phenytoin.",
        "FDA phenytoin label / MedlinePlus", "phenytoin level, seizure frequency"),

    row("phenytoin-vitamin-d", "Phenytoin ↔ vitamin D", "high", PHENYTOIN,
        ["vitamin d", "vitamin d3", "cholecalciferol", "vitamin d2", "ergocalciferol"],
        "Phenytoin accelerates vitamin D metabolism and can cause deficiency over time, "
        "leading to bone loss.",
        "Discuss vitamin D monitoring and supplementation with your neurologist. "
        "Annual bone density review is advisable for long-term phenytoin users.",
        "FDA label / NIH ODS vitamin D", "vitamin D level, bone density"),

    row("phenytoin-calcium", "Phenytoin ↔ calcium", "moderate", PHENYTOIN,
        ["calcium", "calcium carbonate", "calcium citrate"],
        "Calcium can reduce phenytoin absorption when taken at the same time.",
        "Separate calcium supplements from phenytoin by at least 2 hours.",
        "FDA label / MedlinePlus"),
]

# GROUP 18 — Corticosteroids
ROWS += [
    row("steroid-calcium-vitd", "Corticosteroid ↔ calcium + vitamin D", "high", STEROID,
        ["calcium", "calcium carbonate", "calcium citrate", "vitamin d",
         "vitamin d3", "cholecalciferol"],
        "Corticosteroids deplete calcium and interfere with vitamin D metabolism, "
        "significantly increasing osteoporosis risk with long-term use.",
        "Calcium and vitamin D supplementation is generally recommended for patients "
        "on long-term corticosteroids. Discuss doses with your prescriber.",
        "NIH ODS calcium / NIH ODS vitamin D / ACR guidelines",
        "bone density, calcium, vitamin D level"),

    row("steroid-potassium", "Corticosteroid ↔ potassium", "high", STEROID,
        ["potassium", "potassium chloride", "potassium citrate", "potassium gluconate"],
        "Corticosteroids cause potassium loss through the kidneys. Low potassium "
        "can cause muscle weakness and heart rhythm problems.",
        "Discuss potassium monitoring with your clinician if on long-term steroids. "
        "Eat potassium-rich foods or supplement as directed.",
        "FDA corticosteroid labels / MedlinePlus", "serum potassium"),

    row("steroid-zinc", "Corticosteroid ↔ zinc", "moderate", STEROID,
        ["zinc", "zinc gluconate", "zinc picolinate", "zinc citrate"],
        "Long-term corticosteroid use may increase zinc excretion and contribute "
        "to deficiency over time.",
        "Discuss zinc monitoring with your clinician if on long-term steroids.",
        "NIH ODS zinc / MedlinePlus"),
]

# GROUP 19 — Clopidogrel and antiplatelets
ROWS += [
    row("clopidogrel-omega3", "Clopidogrel ↔ omega-3", "high", CLOPI,
        ["fish oil", "omega-3", "omega 3", "epa", "dha", "cod liver oil"],
        "Omega-3 fatty acids have antiplatelet properties that may add to clopidogrel's "
        "blood-thinning effects.",
        "Discuss fish oil dose with your cardiologist. Report unusual bruising or bleeding.",
        "FDA clopidogrel label / NIH ODS", "bleeding signs"),

    row("clopidogrel-vitamin-e", "Clopidogrel ↔ vitamin E", "moderate", CLOPI,
        ["vitamin e", "tocopherol", "tocotrienol"],
        "High-dose vitamin E has antiplatelet activity and may add to clopidogrel's effect.",
        "Avoid high-dose vitamin E with antiplatelet therapy unless your cardiologist approves.",
        "NIH ODS vitamin E / MedlinePlus"),

    row("clopidogrel-ginkgo", "Clopidogrel ↔ ginkgo biloba", "high", CLOPI,
        ["ginkgo", "ginkgo biloba", "egb 761"],
        "Ginkgo inhibits platelet aggregation and can add to clopidogrel's antiplatelet effect.",
        "Avoid ginkgo with antiplatelet medications. Report bleeding or unusual bruising.",
        "MedlinePlus ginkgo / FDA safety communications"),
]

# GROUP 20 — Tamoxifen
ROWS += [
    row("tamoxifen-black-cohosh", "Tamoxifen ↔ black cohosh", "high", TAMOX,
        ["black cohosh", "actaea racemosa", "cimicifuga"],
        "Black cohosh may have oestrogenic activity and could interfere with tamoxifen's "
        "mechanism in oestrogen-sensitive cancers.",
        "Do not use black cohosh with tamoxifen without explicit oncology approval.",
        "NIH NCCIH black cohosh / oncology literature"),

    row("tamoxifen-soy-isoflavones", "Tamoxifen ↔ soy isoflavones", "high", TAMOX,
        ["soy isoflavone", "isoflavone", "genistein", "daidzein", "phytoestrogen"],
        "Soy isoflavones are phytoestrogens that may theoretically interfere with tamoxifen "
        "in oestrogen receptor-positive cancers.",
        "Discuss soy supplement use with your oncologist. Dietary soy is generally "
        "considered different from concentrated isoflavone supplements.",
        "NIH NCCIH / oncology clinical guidelines"),
]

# GROUP 21 — Methotrexate
ROWS += [
    row("methotrexate-folic-acid", "Methotrexate ↔ folic acid", "high", METHO,
        ["folic acid", "folate", "methylfolate", "5-mthf"],
        "Methotrexate works partly by blocking folate pathways. Supplemental folate "
        "is often prescribed to reduce side effects but must be dosed carefully — "
        "too much may reduce methotrexate's effectiveness.",
        "Only take the folic acid dose your rheumatologist or oncologist prescribes. "
        "Do not self-supplement beyond the recommended amount.",
        "ACR methotrexate guidelines / MedlinePlus", "LFTs, CBC"),

    row("methotrexate-vitamin-c-high", "Methotrexate ↔ high-dose vitamin C", "high",
        METHO,
        ["vitamin c", "ascorbic acid", "high dose vitamin c", "megadose vitamin c"],
        "High-dose vitamin C may reduce kidney clearance of methotrexate and increase "
        "toxicity risk.",
        "Avoid high-dose vitamin C supplements with methotrexate. "
        "Discuss any supplementation with your rheumatologist.",
        "Clinical pharmacology literature / MedlinePlus", "methotrexate level, LFTs"),
]

# GROUP 22 — HIV medications
ROWS += [
    row("hiv-st-johns-wort", "HIV medication ↔ St. John's Wort", "critical", HIV_MED,
        ["st. john's wort", "st johns wort", "hypericum"],
        "St. John's Wort potently induces CYP3A4 and P-glycoprotein, dramatically "
        "reducing antiretroviral drug levels and risking HIV resistance.",
        "St. John's Wort is absolutely contraindicated with antiretroviral therapy. "
        "This is not a 'discuss with your doctor' situation — do not combine.",
        "FDA / WHO antiretroviral guidelines / MedlinePlus"),

    row("hiv-garlic-high", "HIV medication ↔ high-dose garlic", "high", HIV_MED,
        ["garlic", "garlic supplement", "aged garlic", "allicin", "garlic extract"],
        "High-dose garlic supplements may reduce levels of some protease inhibitors "
        "through enzyme induction.",
        "Discuss garlic supplement use with your HIV specialist. Dietary garlic "
        "is generally not a concern at normal food amounts.",
        "NIH NCCIH garlic / HIV pharmacology literature"),
]

# GROUP 23 — ADHD medications
ROWS += [
    row("adhd-vitamin-c", "ADHD stimulant ↔ vitamin C", "moderate", ADHD_MED,
        ["vitamin c", "ascorbic acid", "citric acid", "orange juice"],
        "Vitamin C acidifies urine and accelerates elimination of amphetamine-based "
        "ADHD medications, reducing their duration and effectiveness.",
        "Avoid large vitamin C doses or acidic drinks around the time of stimulant doses. "
        "Take vitamin C at a different time of day.",
        "FDA amphetamine label / MedlinePlus"),

    row("adhd-zinc", "ADHD stimulant ↔ zinc", "informational", ADHD_MED,
        ["zinc", "zinc gluconate", "zinc picolinate"],
        "Zinc deficiency has been associated with poorer ADHD symptom control. "
        "Some evidence suggests zinc may modulate stimulant response.",
        "Discuss zinc status with your prescriber. Do not self-supplement zinc "
        "as a substitute for prescribed medication.",
        "NIH ODS zinc / ADHD clinical literature"),
]

# GROUP 24 — Antipsychotics
ROWS += [
    row("antipsychotic-melatonin", "Antipsychotic ↔ melatonin", "moderate", ANTIPSYCH,
        ["melatonin"],
        "Melatonin may add to sedation with antipsychotics. Some antipsychotics "
        "already affect melatonin pathways.",
        "Use lowest effective melatonin dose. Avoid driving or operating machinery "
        "if sedation increases.",
        "MedlinePlus melatonin / clinical literature"),

    row("antipsychotic-caffeine", "Antipsychotic ↔ high caffeine", "moderate", ANTIPSYCH,
        ["caffeine", "energy drink", "guarana"],
        "High caffeine intake can interact with some antipsychotics — caffeine inhibits "
        "adenosine receptors and may affect drug metabolism.",
        "Avoid very high caffeine intake with antipsychotics. Keep intake consistent.",
        "Clinical pharmacology literature / MedlinePlus"),
]

# GROUP 25 — Spironolactone
ROWS += [
    row("spironolactone-potassium", "Spironolactone ↔ potassium", "critical", SPIRO,
        ["potassium", "potassium chloride", "potassium citrate", "potassium gluconate",
         "salt substitute", "nosalt", "nu-salt", "potassium supplement"],
        "Spironolactone is a potassium-sparing diuretic. Added potassium supplements "
        "can cause dangerous hyperkalemia — high potassium can stop the heart.",
        "Do not take potassium supplements or potassium-containing salt substitutes "
        "with spironolactone unless your doctor prescribes them. "
        "Report muscle weakness, numbness, or irregular heartbeat immediately.",
        "FDA spironolactone label / MedlinePlus", "serum potassium, ECG"),

    row("spironolactone-licorice", "Spironolactone ↔ licorice root", "high", SPIRO,
        ["licorice", "licorice root", "glycyrrhizin"],
        "Licorice has mineralocorticoid-like activity and opposes spironolactone's "
        "mechanism, potentially causing sodium retention and potassium loss.",
        "Avoid licorice supplements with spironolactone.",
        "NIH NCCIH licorice / MedlinePlus"),
]

# GROUP 26 — Hormonal contraceptives / estrogen
ROWS += [
    row("contraceptive-st-johns-wort", "Hormonal contraceptive ↔ St. John's Wort", "high", CONTRA,
        ["st. john's wort", "st johns wort", "hypericum"],
        "St. John's Wort induces liver enzymes that break down contraceptive hormones, "
        "reducing their levels and risking breakthrough bleeding and unintended pregnancy.",
        "Use a reliable backup method or avoid St. John's Wort while on hormonal "
        "contraception. Discuss alternatives with your prescriber.",
        "FDA / MedlinePlus drug interaction labeling"),
]

# GROUP 27 — Loop / thiazide diuretics
ROWS += [
    row("diuretic-licorice", "Diuretic ↔ licorice root", "high", DIURETIC,
        ["licorice", "licorice root", "glycyrrhizin"],
        "Licorice promotes potassium loss and sodium retention, worsening the potassium "
        "depletion caused by loop and thiazide diuretics — raising arrhythmia risk.",
        "Avoid licorice supplements with diuretics. Report muscle cramps, weakness, "
        "or palpitations.",
        "NIH NCCIH licorice / MedlinePlus", "serum potassium"),

    row("thiazide-calcium", "Thiazide diuretic ↔ calcium + vitamin D", "moderate",
        ["hydrochlorothiazide", "hctz", "chlorthalidone", "indapamide", "metolazone", "thiazide"],
        ["calcium", "calcium carbonate", "calcium citrate", "vitamin d", "vitamin d3"],
        "Thiazides reduce calcium excretion. With high-dose calcium plus vitamin D this "
        "can raise blood calcium to abnormal levels (hypercalcemia).",
        "Keep calcium and vitamin D within recommended amounts and tell your clinician. "
        "Report nausea, constipation, or confusion.",
        "MedlinePlus / FDA thiazide labeling", "serum calcium"),

    row("diuretic-magnesium", "Loop/thiazide diuretic ↔ magnesium", "informational", DIURETIC,
        ["magnesium", "magnesium citrate", "magnesium glycinate", "magnesium oxide"],
        "Loop and thiazide diuretics increase magnesium loss; supplementation is often "
        "appropriate but should be guided by lab values.",
        "Discuss magnesium monitoring with your clinician. Magnesium supplementation "
        "is commonly recommended rather than avoided.",
        "NIH ODS magnesium / MedlinePlus", "serum magnesium"),
]

# GROUP 28 — Aspirin / antiplatelet
ROWS += [
    row("aspirin-omega3", "Aspirin ↔ omega-3", "moderate", ASPIRIN,
        ["fish oil", "omega-3", "omega 3", "epa", "dha", "cod liver oil"],
        "Omega-3 has mild antiplatelet activity that can add to aspirin's blood-thinning "
        "effect, especially at high fish-oil doses.",
        "Low-dose aspirin with moderate fish oil is common, but tell your clinician and "
        "report unusual bruising or bleeding.",
        "NIH ODS omega-3 / MedlinePlus", "bleeding signs"),

    row("aspirin-ginkgo", "Aspirin ↔ ginkgo biloba", "high", ASPIRIN,
        ["ginkgo", "ginkgo biloba", "egb 761"],
        "Ginkgo inhibits platelet aggregation and combined with aspirin can meaningfully "
        "increase bleeding risk, including rare reports of intracranial bleeding.",
        "Avoid ginkgo with aspirin. Report any unusual bruising, nosebleeds, or bleeding.",
        "MedlinePlus ginkgo / FDA safety communications"),
]

# GROUP 29 — Iron absorption (tannins)
ROWS += [
    row("iron-coffee-tea", "Iron ↔ coffee / tea (tannins)", "moderate",
        ["coffee", "black tea", "green tea", "tea", "tannins"],
        ["iron", "ferrous sulfate", "ferrous gluconate", "ferrous fumarate", "ferrous bisglycinate"],
        "Tannins and polyphenols in coffee and tea bind non-heme iron and can substantially "
        "reduce its absorption when taken together.",
        "Separate iron supplements from coffee or tea by at least 1–2 hours. "
        "Pairing iron with vitamin C improves absorption.",
        "NIH ODS iron / MedlinePlus", pair_type="supplement_supplement"),
]

# GROUP 30 — Additional antiplatelet / bleeding-risk supplements
ROWS += [
    row("aspirin-garlic", "Aspirin ↔ high-dose garlic", "moderate", ASPIRIN,
        ["garlic", "garlic supplement", "aged garlic", "allicin", "garlic extract"],
        "High-dose garlic supplements have mild antiplatelet activity that can add to "
        "aspirin's effect on bleeding.",
        "Normal dietary garlic is fine. Discuss high-dose garlic supplements with your "
        "clinician and report unusual bruising or bleeding.",
        "NIH NCCIH garlic / MedlinePlus"),

    row("aspirin-vitamin-e", "Aspirin ↔ high-dose vitamin E", "moderate", ASPIRIN,
        ["vitamin e", "tocopherol", "tocotrienol"],
        "High-dose vitamin E has antiplatelet activity that may add to aspirin and "
        "increase bleeding risk.",
        "Avoid high-dose vitamin E with regular aspirin unless your clinician approves.",
        "NIH ODS vitamin E / MedlinePlus"),

    row("ssri-ginkgo", "SSRI/SNRI ↔ ginkgo biloba", "moderate", AD,
        ["ginkgo", "ginkgo biloba", "egb 761"],
        "SSRIs and SNRIs can impair platelet function; ginkgo adds antiplatelet activity, "
        "modestly increasing bleeding risk.",
        "Discuss ginkgo use with your prescriber. Report unusual bruising, nosebleeds, "
        "or bleeding.",
        "MedlinePlus ginkgo / clinical bleeding-risk literature"),
]

# GROUP 31 — Potassium-wasting diuretics (disambiguates spironolactone rule)
ROWS += [
    row("diuretic-potassium", "Loop/thiazide diuretic ↔ potassium", "informational", DIURETIC,
        ["potassium", "potassium chloride", "potassium citrate", "potassium gluconate",
         "potassium supplement"],
        "Unlike potassium-sparing diuretics, loop and thiazide diuretics cause potassium "
        "loss. Supplemental potassium is sometimes prescribed — but only under guidance.",
        "Take potassium only as directed by your clinician, who will monitor your levels. "
        "Do not start potassium supplements on your own.",
        "FDA diuretic labeling / MedlinePlus", "serum potassium"),
]

assert len(ROWS) == 118, f"Expected 118 rows, got {len(ROWS)}"
Path(__file__).resolve().parent.joinpath("interactions_db.json").write_text(
    json.dumps(ROWS, indent=2, ensure_ascii=False) + "\n",
    encoding="utf-8",
)
print("Wrote", len(ROWS), "rows to interactions_db.json")
