import requests
import json

url = "https://www.rugbypremierleague.in/feeds/static/Stats_Listing_6.json"

response = requests.get(url)
data = response.json()

print(type(data))
print(len(data))
print(data.keys())
print(type(data["all_stats"]))
print(len(data["all_stats"]))

first_stat = data["all_stats"][0]

print(type(first_stat))
print(first_stat.keys())

first_stat = data["all_stats"][0]

print("Stat Name:", first_stat["stat"])
print("Stat Type:", first_stat["stat_type"])
print("Number of entries:", len(first_stat["data"]))

print(first_stat["data"][0])

# print all 18 leaderboard catagories
for stat in data["all_stats"]:
    print(stat["stat"])

# verifying whther most tackles has the same structure as the first stat
print(data["all_stats"][2]["stat"])  # Most Tackles

print(data["all_stats"][2]["data"][0])