"""
Donchian Channel-berekening. Los bestand i.p.v. een toevoeging aan
utils/indicators.py, om versie-mismatches te voorkomen (zoals eerder
gebeurde toen lokale bestanden niet synchroon liepen met wat hier werd
gebouwd) - dit importeert zelfstandig, geen wijziging aan bestaande
bestanden nodig.
"""

import pandas as pd


def add_donchian_channels(data, window=20):
    """
    Voegt Donchian Channels toe: het hoogste High en laagste Low van de
    afgelopen 'window' dagen, VOORAFGAAND aan vandaag (dus vandaag zelf
    telt niet mee - dat voorkomt dat de huidige candle zijn eigen
    breakout-niveau beïnvloedt, wat een subtiele maar belangrijke fout
    zou zijn).
    """

    data["Donchian_upper"] = data["High"].rolling(window).max().shift(1)
    data["Donchian_lower"] = data["Low"].rolling(window).min().shift(1)

    return data