# import json
# import time
# import requests
# import os
# from dotenv import load_dotenv

# # Carrega variáveis do .env
# load_dotenv()
# API_KEY = os.getenv("GOOGLE_API_KEY")

# # Caminho dos arquivos
# INPUT_FILE = "locais_uem.json"
# OUTPUT_FILE = "locais_uem_atualizado.json"

# GOOGLE_GEOCODE_URL = "https://maps.googleapis.com/maps/api/geocode/json"

# def get_coordinates_google(place_name, cidade="Maringá", estado="Paraná", pais="Brasil"):
#     """Busca coordenadas no Google Maps pelo nome do lugar"""
#     query = f"{place_name}, {cidade}, {estado}, {pais}"
#     params = {
#         "address": query,
#         "key": API_KEY
#     }
#     try:
#         resp = requests.get(GOOGLE_GEOCODE_URL, params=params)
#         resp.raise_for_status()
#         data = resp.json()
#         if data["status"] == "OK":
#             location = data["results"][0]["geometry"]["location"]
#             return [location["lat"], location["lng"]]
#         else:
#             print(f"Google Maps não encontrou: {place_name} ({data['status']})")
#     except Exception as e:
#         print(f"Erro ao buscar {place_name}: {e}")
#     return None

# def atualizar_json():
#     with open(INPUT_FILE, "r", encoding="utf-8") as f:
#         locais = json.load(f)

#     atualizados = {}
#     for nome, coords in locais.items():
#         if nome.startswith("_comment_"):  # mantém comentários
#             atualizados[nome] = coords
#             continue

#         print(f"Buscando coordenadas para: {nome}...")
#         novas_coords = get_coordinates_google(nome)
#         if novas_coords:
#             atualizados[nome] = novas_coords
#             print(f" → Encontrado: {novas_coords}")
#         else:
#             atualizados[nome] = coords  # mantém antigas se falhar
#             print(" → Não encontrado, mantendo as antigas.")

#         time.sleep(0.2)  # respeita limite da API (5 req/s)

#     with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
#         json.dump(atualizados, f, ensure_ascii=False, indent=4)

#     print(f"\n✅ Arquivo atualizado salvo em {OUTPUT_FILE}")

# if __name__ == "__main__":
#     atualizar_json()








import json
import time
import requests

# Caminho dos arquivos
INPUT_FILE = "locais_uem.json"
OUTPUT_FILE = "locais_uem_atualizado.json"

NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"

def get_coordinates_osm(place_name, cidade="Maringá", estado="Paraná", pais="Brasil"):
    """Busca coordenadas no OpenStreetMap pelo nome do lugar"""
    query = f"{place_name}, {cidade}, {estado}, {pais}"
    params = {
        "q": query,
        "format": "json",
        "limit": 1,
        "addressdetails": 0
    }
    headers = {
        "User-Agent": "SeuApp/1.0 (email@dominio.com)"  # OSM exige user-agent válido
    }
    try:
        resp = requests.get(NOMINATIM_URL, params=params, headers=headers, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        if data:
            lat = float(data[0]["lat"])
            lon = float(data[0]["lon"])
            return [lat, lon]
        else:
            print(f"OSM não encontrou: {place_name}")
    except Exception as e:
        print(f"Erro ao buscar {place_name}: {e}")
    return None

def atualizar_json():
    with open(INPUT_FILE, "r", encoding="utf-8") as f:
        locais = json.load(f)

    atualizados = {}
    for nome, coords in locais.items():
        if nome.startswith("_comment_"):  # mantém comentários
            atualizados[nome] = coords
            continue

        print(f"Buscando coordenadas para: {nome}...")
        novas_coords = get_coordinates_osm(nome)
        if novas_coords:
            atualizados[nome] = novas_coords
            print(f" → Encontrado: {novas_coords}")
        else:
            atualizados[nome] = coords  # mantém antigas se falhar
            print(" → Não encontrado, mantendo as antigas.")

        time.sleep(1)  # OSM pede 1 segundo entre requisições

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(atualizados, f, ensure_ascii=False, indent=4)

    print(f"\n✅ Arquivo atualizado salvo em {OUTPUT_FILE}")

if __name__ == "__main__":
    atualizar_json()



