"""Model generations shown in /models analytics and used by scripts (e.g. CEPiK sync).

Each entry's "where" is a SQL condition on the `vehicles v` alias.
"""

STANDARD_MODELS = [
    {
        "id": "alpina_bmw",
        "name": "Alpina BMW (B3 / B5 / D3 / D5)",
        "make": "Alpina",
        "model": "Alpina",
        "variant": "B3 / B5 / D3 / D5",
        "years": "2005–",
        "engine": "Biturbo / D-Turbo · 350-600 HP · RWD/AWD",
        "where": "(v.make = 'Alpina' OR v.variant LIKE '%Alpina%' OR v.model LIKE '%Alpina%')"
    },
    {
        "id": "audi_r8_v8",
        "name": "Audi R8 V8 (Type 42)",
        "make": "Audi",
        "model": "R8",
        "variant": "Type 42 V8",
        "years": "2007–2015",
        "engine": "4.2L V8 FSI · 420-430 HP · Quattro",
        "where": "v.make = 'Audi' AND v.model = 'R8' AND (v.variant LIKE '%V8%' OR v.power_hp < 500)"
    },
    {
        "id": "audi_r8_v10",
        "name": "Audi R8 V10 (Type 42 / 4S)",
        "make": "Audi",
        "model": "R8",
        "variant": "Type 42 / 4S V10",
        "years": "2009–2023",
        "engine": "5.2L V10 FSI · 525-620 HP · Quattro",
        "where": "v.make = 'Audi' AND v.model = 'R8' AND (v.variant LIKE '%V10%' OR v.power_hp >= 500)"
    },
    {
        "id": "rs3_8v",
        "name": "Audi RS3 (8V)",
        "make": "Audi",
        "model": "RS3",
        "variant": "8V",
        "years": "2015–2020",
        "engine": "2.5L TFSI · 367-400 HP · Quattro",
        "where": "v.make = 'Audi' AND (v.model = 'RS3' OR v.variant LIKE '%8V%')"
    },
    {
        "id": "rs4_b85",
        "name": "Audi RS4 B8.5 Avant",
        "make": "Audi",
        "model": "RS4",
        "variant": "B8.5 Avant",
        "years": "2013–2015",
        "engine": "4.2L V8 FSI · 450 HP · Quattro",
        "where": "v.make = 'Audi' AND v.model = 'RS4' AND (v.variant LIKE '%B8%' OR (v.year >= 2012 AND v.year <= 2016)) AND (v.variant NOT LIKE '%B9%' AND (v.year <= 2016 OR v.year IS NULL))"
    },
    {
        "id": "rs4_b9",
        "name": "Audi RS4 B9 Avant",
        "make": "Audi",
        "model": "RS4",
        "variant": "B9 Avant",
        "years": "2017–2024",
        "engine": "2.9L V6 Biturbo · 450 HP · Quattro",
        "where": "v.make = 'Audi' AND v.model = 'RS4' AND (v.variant LIKE '%B9%' OR (v.year >= 2017 AND v.year <= 2024)) AND (v.variant NOT LIKE '%B8%' AND (v.year >= 2017 OR v.year IS NULL))"
    },
    {
        "id": "ttrs",
        "name": "Audi TT RS",
        "make": "Audi",
        "model": "TT",
        "variant": "TT RS",
        "years": "2009–2023",
        "engine": "2.5L TFSI · 340-400 HP · Quattro",
        "where": "v.make = 'Audi' AND (v.model = 'TT RS' OR (v.model = 'TT' AND (v.variant LIKE '%RS%' OR v.power_hp >= 340)))"
    },
    {
        "id": "bmw_135i_e82",
        "name": "BMW 135i (E82/E88)",
        "make": "BMW",
        "model": "Seria 1",
        "variant": "135i E82/E88",
        "years": "2007–2013",
        "engine": "3.0L Turbo N54/N55 · 306 HP · RWD",
        "where": "v.make = 'BMW' AND (v.model = 'Seria 1' OR v.model = '135i') AND (v.variant LIKE '%135i%' OR v.notes LIKE '%135i%')"
    },
    {
        "id": "bmw_1m_e82",
        "name": "BMW 1M Coupe (E82)",
        "make": "BMW",
        "model": "Seria 1",
        "variant": "1M E82",
        "years": "2011–2012",
        "engine": "3.0L Twin-Turbo N54 · 340 HP · RWD",
        "where": "v.make = 'BMW' AND (v.model = 'Seria 1' OR v.model = '1M') AND (v.variant LIKE '%1M%' OR v.notes LIKE '%1M%')"
    },
    {
        "id": "m2_f87",
        "name": "BMW M2 (F87)",
        "make": "BMW",
        "model": "M2",
        "variant": "F87",
        "years": "2016–2021",
        "engine": "3.0L N55/S55 · 370-450 HP · RWD",
        "where": "v.make = 'BMW' AND (v.model = 'M2' OR v.variant LIKE '%F87%') AND (v.variant LIKE '%F87%' OR (v.year >= 2015 AND v.year <= 2021))"
    },
    {
        "id": "m2_g87",
        "name": "BMW M2 (G87)",
        "make": "BMW",
        "model": "M2",
        "variant": "G87",
        "years": "2023–",
        "engine": "3.0L Twin-Turbo S58 · 460-480 HP · RWD",
        "where": "v.make = 'BMW' AND (v.model = 'M2' OR v.variant LIKE '%G87%') AND (v.variant LIKE '%G87%' OR v.year >= 2022)"
    },
    {
        "id": "bmw_m3_e46",
        "name": "BMW M3 (E46)",
        "make": "BMW",
        "model": "M3",
        "variant": "E46 M3",
        "years": "2000–2006",
        "engine": "3.2L NA S54 · 343 HP · RWD",
        "where": "v.make = 'BMW' AND v.model = 'M3' AND (v.variant LIKE '%E46%' OR (v.year >= 2000 AND v.year <= 2006))"
    },
    {
        "id": "m3_f80",
        "name": "BMW M3 (F80)",
        "make": "BMW",
        "model": "M3",
        "variant": "F80",
        "years": "2014–2018",
        "engine": "3.0L Twin-Turbo S55 · 431-460 HP · RWD",
        "where": "v.make = 'BMW' AND (v.model = 'M3' OR v.variant LIKE '%F80%') AND (v.variant LIKE '%F80%' OR (v.year >= 2014 AND v.year <= 2019))"
    },
    {
        "id": "m4_f82",
        "name": "BMW M4 (F82)",
        "make": "BMW",
        "model": "M4",
        "variant": "F82",
        "years": "2014–2020",
        "engine": "3.0L Twin-Turbo S55 · 431-500 HP · RWD",
        "where": "v.make = 'BMW' AND (v.model = 'M4' OR v.variant LIKE '%F82%' OR v.variant LIKE '%F83%') AND (v.year >= 2014 AND v.year <= 2020)"
    },
    {
        "id": "bmw_m5_e39",
        "name": "BMW M5 (E39)",
        "make": "BMW",
        "model": "M5",
        "variant": "E39 M5",
        "years": "1998–2003",
        "engine": "4.9L V8 NA S62 · 400 HP · RWD",
        "where": "v.make = 'BMW' AND v.model = 'M5' AND (v.variant LIKE '%E39%' OR (v.year >= 1998 AND v.year <= 2003))"
    },
    {
        "id": "x3_m_f97",
        "name": "BMW X3 M (F97)",
        "make": "BMW",
        "model": "X3 M",
        "variant": "F97",
        "years": "2019–2024",
        "engine": "3.0L Twin-Turbo S58 · 480-510 HP · AWD",
        "where": "v.make = 'BMW' AND (v.model = 'X3 M' OR (v.model = 'X3' AND v.variant LIKE '%F97%')) AND (v.variant NOT LIKE '%M40i%' AND v.model NOT LIKE '%M40i%')"
    },
    {
        "id": "x3_m40i_g01",
        "name": "BMW X3 M40i (G01)",
        "make": "BMW",
        "model": "X3",
        "variant": "M40i G01",
        "years": "2017–2024",
        "engine": "3.0L Turbo B58 · 360 HP · AWD",
        "where": "v.make = 'BMW' AND (v.model = 'X3' OR v.model = 'X3 M40i') AND (v.variant LIKE '%M40i%' OR v.variant LIKE '%G01%') AND (v.model != 'X3 M' AND v.variant NOT LIKE '%F97%')"
    },
    {
        "id": "bmw_z3_m",
        "name": "BMW Z3 M (Coupe / Roadster)",
        "make": "BMW",
        "model": "Z3",
        "variant": "Z3 M",
        "years": "1997–2002",
        "engine": "3.2L NA S50/S54 · 321-325 HP · RWD",
        "where": "v.make = 'BMW' AND v.model = 'Z3' AND (v.variant LIKE '%Z3 M%' OR v.power_hp >= 300)"
    },
    {
        "id": "honda_s2000",
        "name": "Honda S2000",
        "make": "Honda",
        "model": "S2000",
        "variant": "AP1 / AP2",
        "years": "1999–2009",
        "engine": "2.0L VTEC F20C · 240 HP · RWD",
        "where": "v.make = 'Honda' AND v.model = 'S2000'"
    },
    {
        "id": "a45_w176",
        "name": "Mercedes A45 AMG (W176)",
        "make": "Mercedes-Benz",
        "model": "Klasa A",
        "variant": "W176 A45 AMG",
        "years": "2013–2018",
        "engine": "2.0L Turbo M133 · 360-381 HP · 4MATIC",
        "where": "v.make = 'Mercedes-Benz' AND (v.model = 'Klasa A' OR v.model LIKE '%A 45%' OR v.model LIKE '%A45%') AND (v.variant LIKE '%W176%' OR v.variant LIKE '%A45%' OR v.power_hp >= 360)"
    },
    {
        "id": "c63_w204",
        "name": "Mercedes C63 AMG (W204)",
        "make": "Mercedes-Benz",
        "model": "Klasa C",
        "variant": "W204 C63 AMG",
        "years": "2008–2015",
        "engine": "6.2L V8 M156 · 457-507 HP · RWD",
        "where": "v.make = 'Mercedes-Benz' AND (v.variant LIKE '%W204%' OR v.variant LIKE '%C63%' OR v.variant LIKE '%C 63%' OR (v.model = 'Klasa C' AND (v.power_hp >= 450 OR v.engine_cc > 6000)))"
    },
    {
        "id": "cl55_c215",
        "name": "Mercedes CL55 AMG (C215)",
        "make": "Mercedes-Benz",
        "model": "CL",
        "variant": "CL55 AMG C215",
        "years": "2002–2006",
        "engine": "5.4L V8 Kompressor M113K · 500 HP · RWD",
        "where": "v.make = 'Mercedes-Benz' AND (v.model = 'CL' OR v.variant LIKE '%CL55%' OR v.variant LIKE '%C215%') AND (v.variant LIKE '%CL55%' OR v.power_hp >= 490)"
    },
    {
        "id": "clk63_w209",
        "name": "Mercedes CLK63 AMG (W209)",
        "make": "Mercedes-Benz",
        "model": "Klasa CLK",
        "variant": "W209 CLK 63 AMG",
        "years": "2006–2009",
        "engine": "6.2L V8 M156 · 481 HP · RWD",
        "where": "v.make = 'Mercedes-Benz' AND (v.model = 'Klasa CLK' OR v.variant LIKE '%CLK 63%' OR v.variant LIKE '%CLK63%')"
    },
    {
        "id": "cls55_c219",
        "name": "Mercedes CLS55 AMG (C219)",
        "make": "Mercedes-Benz",
        "model": "CLS",
        "variant": "C219 CLS 55 AMG",
        "years": "2004–2006",
        "engine": "5.4L V8 Kompressor M113K · 476 HP · RWD",
        "where": "v.make = 'Mercedes-Benz' AND (v.variant LIKE '%C219%' OR v.variant LIKE '%CLS 55%' OR v.variant LIKE '%CLS55%' OR (v.model = 'CLS' AND (v.power_hp >= 460 OR v.engine_cc = 5439)))"
    },
    {
        "id": "e55_w211",
        "name": "Mercedes E55 AMG (W211)",
        "make": "Mercedes-Benz",
        "model": "Klasa E",
        "variant": "W211 E55 AMG",
        "years": "2003–2006",
        "engine": "5.4L V8 Kompressor M113K · 476 HP · RWD",
        "where": "v.make = 'Mercedes-Benz' AND (v.variant LIKE '%W211%' OR v.variant LIKE '%E55%' OR v.variant LIKE '%E 55%' OR (v.model = 'Klasa E' AND (v.power_hp >= 460 OR v.engine_cc = 5439)))"
    },
    {
        "id": "g55_w463",
        "name": "Mercedes G55 AMG (W463)",
        "make": "Mercedes-Benz",
        "model": "Klasa G",
        "variant": "G55 AMG W463",
        "years": "2004–2012",
        "engine": "5.4L V8 Kompressor M113K · 476-507 HP · 4WD",
        "where": "v.make = 'Mercedes-Benz' AND (v.model = 'Klasa G' OR v.variant LIKE '%G55%' OR v.variant LIKE '%W463%') AND (v.variant LIKE '%G55%' OR v.power_hp >= 470)"
    },
    {
        "id": "gla45_x156",
        "name": "Mercedes GLA45 AMG (X156)",
        "make": "Mercedes-Benz",
        "model": "GLA",
        "variant": "GLA45 AMG X156",
        "years": "2014–2019",
        "engine": "2.0L Turbo M133 · 360-381 HP · 4MATIC",
        "where": "v.make = 'Mercedes-Benz' AND (v.model = 'GLA' OR v.variant LIKE '%GLA45%' OR v.variant LIKE '%X156%') AND (v.variant LIKE '%GLA45%' OR v.power_hp >= 360)"
    },
    {
        "id": "s55_w220",
        "name": "Mercedes S55 AMG (W220)",
        "make": "Mercedes-Benz",
        "model": "Klasa S",
        "variant": "S55 AMG W220",
        "years": "2002–2005",
        "engine": "5.4L V8 Kompressor M113K · 500 HP · RWD",
        "where": "v.make = 'Mercedes-Benz' AND (v.model = 'Klasa S' OR v.variant LIKE '%S55%' OR v.variant LIKE '%W220%') AND (v.variant LIKE '%S55%' OR v.power_hp >= 490)"
    },
    {
        "id": "sl55_r230",
        "name": "Mercedes SL55 AMG (R230)",
        "make": "Mercedes-Benz",
        "model": "SL",
        "variant": "SL55 AMG R230",
        "years": "2001–2008",
        "engine": "5.4L V8 Kompressor M113K · 476-517 HP · RWD",
        "where": "v.make = 'Mercedes-Benz' AND (v.model = 'SL' OR v.variant LIKE '%SL55%' OR v.variant LIKE '%R230%') AND (v.variant LIKE '%SL55%' OR v.power_hp >= 470)"
    },
    {
        "id": "cayman_987",
        "name": "Porsche Cayman (987)",
        "make": "Porsche",
        "model": "Cayman",
        "variant": "Cayman 987",
        "years": "2005–2012",
        "engine": "3.4L Flat-6 NA · 295-330 HP · RWD",
        "where": "v.make = 'Porsche' AND v.model = 'Cayman' AND (v.variant LIKE '%987%' OR (v.year >= 2005 AND v.year <= 2012))"
    },
    {
        "id": "cayman_981",
        "name": "Porsche Cayman (981)",
        "make": "Porsche",
        "model": "Cayman",
        "variant": "Cayman 981 / GT4",
        "years": "2013–2016",
        "engine": "3.4L / 3.8L Flat-6 NA · 325-385 HP · RWD",
        "where": "v.make = 'Porsche' AND v.model = 'Cayman' AND (v.variant LIKE '%981%' OR (v.year >= 2013 AND v.year <= 2016))"
    },
    {
        "id": "cayman_718",
        "name": "Porsche 718 Cayman",
        "make": "Porsche",
        "model": "718 Cayman",
        "variant": "718 Cayman",
        "years": "2016–",
        "engine": "2.5L Turbo / 4.0L NA · 350-500 HP · RWD",
        "where": "v.make = 'Porsche' AND (v.model = '718' OR v.model = 'Cayman' OR v.model = '718 Cayman') AND (v.variant LIKE '%718%' OR v.year >= 2016)"
    },
    {
        "id": "macan_gen1",
        "name": "Porsche Macan Gen 1",
        "make": "Porsche",
        "model": "Macan",
        "variant": "Macan Gen 1 (S/GTS/Turbo)",
        "years": "2014–2018",
        "engine": "3.0L / 3.6L V6 Biturbo · 340-440 HP · AWD",
        "where": "v.make = 'Porsche' AND v.model = 'Macan' AND (v.variant LIKE '%Macan%' OR (v.year >= 2014 AND v.year <= 2018))"
    },
    {
        "id": "gr_yaris",
        "name": "Toyota GR Yaris",
        "make": "Toyota",
        "model": "GR Yaris",
        "variant": "GR Yaris",
        "years": "2020–",
        "engine": "1.6L 3-cyl Turbo · 261-280 HP · AWD",
        "where": "v.make = 'Toyota' AND (v.model = 'GR Yaris' OR (v.model = 'Yaris' AND (v.variant LIKE '%GR%' OR v.power_hp >= 250)))"
    },
]
STANDARD_MODELS = sorted(STANDARD_MODELS, key=lambda m: (m["make"], m["name"]))

DEFAULT_MODEL_ID = "x3_m40i_g01"


def get_model(model_id):
    """Return the catalog entry for model_id, or None."""
    return next((m for m in STANDARD_MODELS if m["id"] == model_id), None)
