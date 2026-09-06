import json

with open('notebooks/1_2_settlement_classification.ipynb', 'r', encoding='utf-8') as f:
    data = json.load(f)

for cell in data['cells']:
    if cell['cell_type'] == 'code' and any('classified_img = results' in line for line in cell.get('source', [])):
        new_source = []
        for line in cell['source']:
            if 'classified_img = results' in line:
                new_source.append('classified_img = results["classified"][2024]\n')
            elif '# 4. Reduce LST' in line:
                new_source.append('# 4. Reduce LST and Area over the vectors\n')
            elif 'def add_lst(feature):' in line:
                new_source.append('def add_lst_and_area(feature):\n')
            elif 'return feature.set(' in line:
                new_source.append('    area_sqm = feature.geometry().area()\n')
                new_source.append('    return feature.set(\'mean_lst\', mean_lst).set(\'area_sqm\', area_sqm)\n')
            elif 'print("Calculating Mean LST per polygon' in line:
                new_source.append('print("Calculating Mean LST and Area per polygon (this may take a minute)...")\n')
            elif 'informal_with_lst = vectors.map(add_lst)' in line:
                new_source.append('informal_with_lst = vectors.map(add_lst_and_area)\n')
            else:
                new_source.append(line)
        cell['source'] = new_source

with open('notebooks/1_2_settlement_classification.ipynb', 'w', encoding='utf-8') as f:
    json.dump(data, f, indent=1)

print("Notebook updated successfully.")
