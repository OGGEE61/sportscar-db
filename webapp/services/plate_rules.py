"""Polish registration plates: which strings can be one, and how to fix an OCR reading of one.

Source: Rozporządzenie Ministra Infrastruktury z 8 listopada 2024 r. w sprawie rejestracji
i oznaczania pojazdów (Dz.U. 2024 poz. 1709): § 30 ust. 1 (25 letters, no Q), § 30 ust. 2 (the
layouts below), § 31 ust. 1 (no B, D, I, O, Z in the vehicle part), annex 13 (district codes).

An OCR reading is fixed by the rules alone: a district code is letters only and must be on the
annex 13 list, and the vehicle part never has B, D, I, O or Z, so an "O" read there is a 0. Only
where a layout allows both a letter and a digit (S/5, G/6) does a reading have several candidates;
CEPiK decides between them (scripts/fetch_cepik.py).
"""
import re
from itertools import product

LETTERS = frozenset("ABCDEFGHIJKLMNOPRSTUVWXYZ")
VEHICLE_LETTERS = LETTERS - frozenset("BDIOZ")

# Voivodeship letter + district code, annex 13 of the 2024 regulation (380 districts)
DISTRICTS = frozenset("""
    AA AB ABR ACI AD AE AF AG AGM AGR AGS AH AI AJ AK AKZ AL ALI ALS AM AMA AML AN AND AO AOR AOS AOT
    AP APA API APL APN APP APR APS APU APW APX APY APZ AR ARA AS ASC ASE ASI ASK ASZ AT AU AV AW AWE
    AWL AWY AX AY AZ AZU AZW AZY
    BAU BBI BGR BHA BI BIA BIB BKL BL BLM BMN BS BSE BSI BSK BSU BWM BZA
    CAL CB CBC CBR CBY CCH CG CGD CGR CIN CLI CMG CNA CRA CRY CSE CSW CT CTR CTU CW CWA CWL CZN
    DB DBA DBL DDZ DGL DGR DJ DJA DJE DKA DKL DL DLB DLE DLU DLW DMI DOA DOL DPL DSR DST DSW DTR DW DWL
    DWR DX DZA DZG DZL
    EBE EBR ED EKU EL ELA ELC ELE ELW EOP EP EPA EPD EPI EPJ ERA ERW ES ESI ESK ETM EWE EWI EZD EZG
    FG FGW FKR FMI FNW FSD FSL FSU FSW FWS FZ FZA FZG FZI
    GA GBY GCH GCZ GD GDA GKA GKS GKW GKY GKZ GLE GMB GND GPU GS GSL GSP GST GSZ GTC GWE GWO
    IB IBE IBI IBL IBN IC ICI ICN ICZ ID IE IG IGL IH II IJ IJZ IK IKL IL ILU IM IMI IMY IO IPI IPS IR
    IRB IRC IRS IT ITA IW IWD IWZ IY IZ IZA IZO IZY
    JBA JBC JBR JCH JDA JGR JK JLI JMI JMY JN JNS JNT JOL JOS JPR JR JRA JRK JSU JT JTA JTT JWA JWI
    KBA KBC KBR KCH KDA KGR KK KLI KMI KMY KN KNS KNT KOL KOS KPR KR KRA KRK KSU KT KTA KTT KWA KWI
    LB LBI LBL LC LCH LHR LJA LKR LKS LLB LLE LLU LOP LPA LPU LRA LRY LSW LTM LU LUB LWL LZ LZA
    MA MCH MCT MGN MGO MGS MJA MK MKA MKE MKL MKN MKO MKR MKS ML MLE MMI MN MNT MO MOB MOS MOT MOZ MP
    MPL MRA MSE MSL MSR MSZ MTU MWA MWL MWR MX MY MZ MZL
    NBA NBR NDZ NE NEB NEL NGI NGO NIL NKE NLI NMR NNI NNM NO NOE NOL NOS NOT NOX NPI NSZ NWE
    OB OGL OK OKL OKR ONA ONY OOL OP OPO OPR OST
    PA PCH PCT PGN PGO PGS PJA PK PKA PKE PKL PKN PKO PKR PKS PL PLE PMI PN PNT PO POB POS POT POZ PP
    PPL PRA PSE PSL PSR PSZ PTU PWA PWL PWR PX PY PZ PZL
    RBI RBR RDE RJA RJS RK RKL RKR RLA RLE RLS RLU RMI RNI RP RPR RPZ RRS RSA RSR RST RT RTA RZ RZE RZR
    RZZ
    SB SBE SBI SBL SBN SC SCI SCN SCZ SD SE SG SGL SH SI SJ SJZ SK SKL SL SLU SM SMI SMY SO SPI SPS SR
    SRB SRC SRS ST STA SW SWD SWZ SY SZ SZA SZO SZY
    TBU TJE TK TKA TKC TKI TKM TKN TKP TLW TOP TOS TPI TSA TSK TST TSZ
    VB VBA VBL VDZ VGL VGR VJ VJA VJE VKA VKL VL VLB VLE VLU VLW VMI VOA VOL VPL VSR VST VSW VTR VW VWL
    VWR VX VZA VZG VZL
    WA WB WBR WCI WD WE WF WG WGM WGR WGS WH WI WJ WK WKZ WL WLI WLS WM WMA WML WN WND WO WOR WOS WOT
    WP WPA WPI WPL WPN WPP WPR WPS WPU WPW WPX WPY WPZ WR WRA WS WSC WSE WSI WSK WSZ WT WU WV WW WWE
    WWL WWY WX WY WZ WZU WZW WZY
    XA XBY XCH XCZ XD XDA XKA XKS XKW XKY XKZ XLE XMB XND XPU XS XSL XSP XST XSZ XTC XWE XWO
    YBI YBR YDE YJA YJS YK YKL YKR YLA YLE YLS YLU YMI YNI YP YPR YPZ YRS YSA YSR YST YT YTA YZ YZE YZR
    YZZ
    ZBI ZCH ZDR ZGL ZGR ZGY ZK ZKA ZKL ZKO ZLO ZMY ZPL ZPY ZS ZSD ZSL ZST ZSW ZSZ ZWA ZZ
""".split())
VOIVODESHIPS = frozenset(code[0] for code in DISTRICTS)

# Vehicle part after the district code, by the code's length. L letter, C digit, N digit 1-9;
# a run of digits is never all zeros ("od 001 do 999").
LAYOUTS = {
    2: ("CCCCC", "CCCCL", "CCCLL", "NLCCC", "NLLCC",                        # ordinary, § 30 ust. 2 pkt 1a
        "CCL", "CCC"),                                                      # classic, pkt 5a
    3: ("LCCC", "CCLL", "NLCC", "CCLN", "NLLN", "LLCC", "CCCCC", "CCCCL", "CCCLL",  # ordinary, pkt 1b
        "NL", "CC", "LN"),                                                  # classic, pkt 5b
}
# After the voivodeship letter alone: reduced plates (pkt 2), for cars with a small plate recess,
# e.g. many cars from the USA
REDUCED = ("CCC", "CCL", "NLN", "LCC", "NLL", "LLN", "LNL")
# After a voivodeship letter and a digit (0 included): temporary plates (pkt 6) and individual ones
# (pkt 4): three letters of the owner's choice (any of the 25), then up to two more, which may be
# digits, and digits only at the end (AMG55, ABCDE, ABC1).
# CEPiK also confirms older individual plates outside that pattern (W0HT88, S0GR8, R0C63, Z7M4X):
# all start with a letter and have at most two digits. Those are recognised, but ranked after
# every other reading, so an OCR misreading is not taken for one. An individual plate is never corrected.
TEMPORARY = ("CCCC", "CCCL")
INDIVIDUAL = ("LLL", "LLLL", "LLLC", "LLLLL", "LLLLC", "LLLCC")
OLD_INDIVIDUAL = tuple(sorted({"L" + "".join(rest) for n in (3, 4, 5) for rest in product("LC", repeat=n - 1)
                               if rest.count("C") <= 2} - set(INDIVIDUAL)))

# What OCR mistakes for what. Swapping S/5 or G/6 is a guess (both are allowed in the vehicle part);
# the others are forced by the slot, e.g. a digit read in a district code.
AS_LETTER = {"0": "O", "1": "I", "2": "Z", "5": "S", "6": "G", "8": "B"}
AS_DIGIT = {"O": "0", "D": "0", "Q": "0", "U": "0", "I": "1", "Z": "2", "S": "5", "G": "6", "B": "8"}
GUESSES = {("S", "5"), ("5", "S"), ("G", "6"), ("6", "G")}


def normalize(text) -> str:
    return re.sub(r"[^A-Z0-9]", "", (text or "").upper())


def _fit(chars: str, layout: str, letters: frozenset, vehicle_part: bool = True):
    """chars forced into layout, or None; with the number of changes and of guessed changes.
    In a vehicle part a run of digits is never all zeros; a voivodeship digit may be 0."""
    if len(chars) != len(layout):
        return None
    out, changes, guesses = [], 0, 0
    for ch, slot in zip(chars, layout):
        if slot == "L":
            new = ch if ch in letters else AS_LETTER.get(ch)
            if new not in letters:
                return None
        else:
            new = ch if ch.isdigit() else AS_DIGIT.get(ch)
            if new is None or (slot == "N" and new == "0"):
                return None
        if new != ch:
            changes += 1
            guesses += (ch, new) in GUESSES
        out.append(new)
    fixed = "".join(out)
    if vehicle_part and any(set(run) == {"0"} for run in re.findall(r"\d+", "".join(
            c if s in "CN" else " " for c, s in zip(fixed, layout)))):
        return None
    return fixed, changes, guesses


def _readings(text: str):
    """Every way to read text as a Polish plate: (plate, changes, guesses, kind)."""
    for plen, layouts in LAYOUTS.items():
        head = _fit(text[:plen], "L" * plen, LETTERS, vehicle_part=False)
        if not head or head[0] not in DISTRICTS:
            continue
        for layout in layouts:
            if len(text) == plen + len(layout) and (tail := _fit(text[plen:], layout, VEHICLE_LETTERS)):
                yield head[0] + tail[0], head[1] + tail[1], head[2] + tail[2], "zwyczajna"
    head = _fit(text[:1], "L", LETTERS, vehicle_part=False)
    if head and head[0] in VOIVODESHIPS:
        for layout in REDUCED:
            if len(text) == 1 + len(layout) and (tail := _fit(text[1:], layout, VEHICLE_LETTERS)):
                yield head[0] + tail[0], head[1] + tail[1], head[2] + tail[2], "zmniejszona"
    head = _fit(text[:2], "LC", LETTERS, vehicle_part=False)
    if head and head[0][0] in VOIVODESHIPS:
        for kind, layouts, letters in (("tymczasowa", TEMPORARY, VEHICLE_LETTERS), ("indywidualna", INDIVIDUAL, LETTERS),
                                       ("indywidualna (dawna)", OLD_INDIVIDUAL, LETTERS)):
            for layout in layouts:
                if len(text) == 2 + len(layout) and (tail := _fit(text[2:], layout, letters)):
                    yield head[0] + tail[0], head[1] + tail[1], head[2] + tail[2], kind


def plate_kind(plate):
    """'zwyczajna', 'zmniejszona', 'tymczasowa' or 'indywidualna' when plate is a valid Polish plate as it stands, else None."""
    text = normalize(plate)
    kinds = [kind for _, changes, _, kind in _readings(text) if changes == 0]
    return next((k for k in kinds if "dawna" not in k), "indywidualna" if kinds else None)


def is_polish_plate(plate) -> bool:
    return plate_kind(plate) is not None


def plate_candidates(reading, limit: int = 4) -> list:
    """The Polish plates an OCR (or typed) reading can stand for, likeliest first: the reading itself
    when valid, then fixes forced by the rules, then guesses (S/5, G/6). Individual plates are taken
    as read, since their owner picks any letters. Empty when nothing fits a Polish plate."""
    text = normalize(reading)
    best = {}
    for fixed, changes, guesses, kind in _readings(text):
        if kind.startswith("indywidualna") and changes:
            continue
        key = ("dawna" in kind, guesses, changes)
        if fixed not in best or key < best[fixed]:
            best[fixed] = key
    return [p for p, _ in sorted(best.items(), key=lambda item: (item[1], item[0]))][:limit]
