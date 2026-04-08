"""
URL → organisation-slug mappning.
Kärnkomponent i /analyze-endpointen.
73 domäner täcker alla 37 seedade organisationer.
"""
from urllib.parse import urlparse

# slug = None → känd domän men ej politiskt klassificerad
DOMAIN_MAP: dict[str, str | None] = {
    # ──── Riksmedier ────────────────────────────────────────────────────────
    "dn.se":                            "dagens-nyheter",
    "www.dn.se":                        "dagens-nyheter",
    "svd.se":                           "svenska-dagbladet",
    "www.svd.se":                       "svenska-dagbladet",
    "aftonbladet.se":                   "aftonbladet",
    "www.aftonbladet.se":               "aftonbladet",
    "expressen.se":                     "expressen",
    "www.expressen.se":                 "expressen",
    "gt.expressen.se":                  "expressen",
    "kvallsposten.expressen.se":        "expressen",
    "gp.se":                            "goteborgs-posten",
    "www.gp.se":                        "goteborgs-posten",
    "di.se":                            "dagens-industri",
    "www.di.se":                        "dagens-industri",
    "tv.di.se":                         "dagens-industri",
    "sydsvenskan.se":                   "sydsvenskan",
    "www.sydsvenskan.se":               "sydsvenskan",
    "svt.se":                           "svt-nyheter",
    "www.svt.se":                       "svt-nyheter",
    "nyheter.svt.se":                   "svt-nyheter",
    "sr.se":                            "sr-ekot",
    "www.sr.se":                        "sr-ekot",
    "sverigesradio.se":                 "sr-ekot",
    "www.sverigesradio.se":             "sr-ekot",
    # ──── Alternativmedier ──────────────────────────────────────────────────
    "etc.se":                           "etc",
    "www.etc.se":                       "etc",
    "syre.se":                          "syre",
    "www.syre.se":                      "syre",
    "kvartal.se":                       "kvartal",
    "www.kvartal.se":                   "kvartal",
    "nyheteridag.se":                   "nyheter-idag",
    "www.nyheteridag.se":               "nyheter-idag",
    "samtiden.se":                      "samtiden",
    "www.samtiden.se":                  "samtiden",
    "samhallsnytt.se":                  "samhallsnytt",
    "www.samhallsnytt.se":              "samhallsnytt",
    "dagensarena.se":                   "dagens-arena",
    "www.dagensarena.se":               "dagens-arena",
    "cogito.nu":                        "cogito",
    "www.cogito.nu":                    "cogito",
    # ──── Tankesmedjor höger ────────────────────────────────────────────────
    "timbro.se":                        "timbro",
    "www.timbro.se":                    "timbro",
    "ifn.se":                           "ifn",
    "www.ifn.se":                       "ifn",
    "ratio.se":                         "ratio",
    "www.ratio.se":                     "ratio",
    "naringslivets-medieinstitut.se":   "nmi",
    "www.naringslivets-medieinstitut.se": "nmi",
    # ──── Tankesmedjor center ───────────────────────────────────────────────
    "fores.se":                         "fores",
    "www.fores.se":                     "fores",
    "sns.se":                           "sns",
    "www.sns.se":                       "sns",
    # ──── Tankesmedjor vänster ──────────────────────────────────────────────
    "katalys.org":                      "katalys",
    "www.katalys.org":                  "katalys",
    "arenaide.se":                      "arena-ide",
    "www.arenaide.se":                  "arena-ide",
    "tankesmedjantiden.se":             "tankesmedjan-tiden",
    "www.tankesmedjantiden.se":         "tankesmedjan-tiden",
    "futurion.se":                      "futurion",
    "www.futurion.se":                  "futurion",
    # ──── Politiska partier ─────────────────────────────────────────────────
    "socialdemokraterna.se":            "socialdemokraterna",
    "www.socialdemokraterna.se":        "socialdemokraterna",
    "moderaterna.se":                   "moderaterna",
    "www.moderaterna.se":               "moderaterna",
    "sd.se":                            "sverigedemokraterna",
    "www.sd.se":                        "sverigedemokraterna",
    "centerpartiet.se":                 "centerpartiet",
    "www.centerpartiet.se":             "centerpartiet",
    "vansterpartiet.se":                "vansterpartiet",
    "www.vansterpartiet.se":            "vansterpartiet",
    "mp.se":                            "miljopartiet",
    "www.mp.se":                        "miljopartiet",
    "liberalerna.se":                   "liberalerna",
    "www.liberalerna.se":               "liberalerna",
    "kd.se":                            "kristdemokraterna",
    "www.kd.se":                        "kristdemokraterna",
    # ──── Officiella källor ─────────────────────────────────────────────────
    "riksdagen.se":                     "riksdagen",
    "www.riksdagen.se":                 "riksdagen",
    "data.riksdagen.se":                "riksdagen",
    "riksdagslistan.riksdagen.se":      "riksdagen",
    "regeringen.se":                    "regeringskansliet",
    "www.regeringen.se":                "regeringskansliet",
    "government.se":                    "regeringskansliet",
    "www.government.se":                "regeringskansliet",
    # ──── Kända domäner utan klassificering ─────────────────────────────────
    "thelocal.se":                      None,
    "realtid.se":                       None,
    "resume.se":                        None,
    "dagensmedia.se":                   None,
    "scb.se":                           None,
}


def extract_domain(url: str) -> str:
    """Extrahera hostname från URL."""
    try:
        if "://" not in url:
            url = f"https://{url}"
        return urlparse(url).hostname or url.lower().strip()
    except Exception:
        return url.lower().strip()
