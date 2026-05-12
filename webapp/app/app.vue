<script setup lang="ts">
import { onMounted, ref, onUnmounted, watch } from 'vue'
import maplibregl from 'maplibre-gl'
import 'maplibre-gl/dist/maplibre-gl.css'

// Our Tab Structure
const tabs = ['Exposure (Part 1)', 'Sensitivity (Part 2)', 'Adaptive Capacity (Part 3)']
const activeTab = ref(tabs[0])

// Our pre-calculated colored maps
const layerGroups = {
  'Exposure (Part 1)': {
    lst_2020: { name: 'LST 2020', file: '/maps/lst_2020.png', unit: '°C', min: 20, max: 45 },
    lst_2022: { name: 'LST 2022', file: '/maps/lst_2022.png', unit: '°C', min: 20, max: 45 },
    lst_2024: { name: 'LST 2024', file: '/maps/lst_2024.png', unit: '°C', min: 20, max: 45 }
  },
  'Sensitivity (Part 2)': {
    sensitivity_population: { name: 'Total Population', file: '/maps/sensitivity_population.png', unit: 'People/ha', min: 0, max: 1200 },
    sensitivity_elderly: { name: 'Elderly Pop (60+)', file: '/maps/sensitivity_elderly.png', unit: 'People/ha', min: 0, max: 150 },
    sensitivity_children: { name: 'Children Pop (<5)', file: '/maps/sensitivity_children_population.png', id: 'sensitivity_children_population', file_override: true, unit: 'People/ha', min: 0, max: 200 }
  },
  'Adaptive Capacity (Part 3)': {
    retail_proximity: { name: 'Retail Proximity', file: '/maps/retail_proximity.png', unit: 'Score', min: 0, max: 1 },
    health_proximity: { name: 'Healthcare Proximity', file: '/maps/health_proximity.png', unit: 'Score', min: 0, max: 1 },
    water_proximity: { name: 'Water Access', file: '/maps/water_proximity.png', unit: 'Score', min: 0, max: 1 },
    green_proximity: { name: 'Green Spaces', file: '/maps/green_proximity.png', unit: 'Score', min: 0, max: 1 },
    cooling_proximity: { name: 'Cooling Centers', file: '/maps/cooling_proximity.png', unit: 'Score', min: 0, max: 1 },
    mobility_proximity: { name: 'Road Density', file: '/maps/mobility_proximity.png', unit: 'Score', min: 0, max: 1 }
  }
}

// Fixed the sensitivity_children ID to match the filename exactly
const getFile = (id: string, info: any) => {
  if (id === 'sensitivity_children') return '/maps/sensitivity_children_population.png'
  return info.file
}

// Opacity state for every layer (0 to 100)
const opacities = ref<Record<string, number>>({})
Object.entries(layerGroups).forEach(([groupName, group]) => {
  Object.keys(group).forEach(id => {
    opacities.value[id] = 0 // Everything hidden by default
  })
})

// Logic to find the "active" layer for the legend
const activeLegendLayer = ref<any>(null)

watch(opacities, (newOps) => {
  if (!map || !map.isStyleLoaded()) return
  
  let maxOpacity = 0
  let topId = ''

  Object.entries(newOps).forEach(([id, val]) => {
    if (map!.getLayer(`${id}-layer`)) {
      map!.setPaintProperty(`${id}-layer`, 'raster-opacity', val / 100)
    }
    if (val > maxOpacity) {
      maxOpacity = val
      topId = id
    }
  })

  // Update legend
  if (maxOpacity > 0) {
    for (const group of Object.values(layerGroups)) {
      if (group[topId as keyof typeof group]) {
        activeLegendLayer.value = { ...group[topId as keyof typeof group], id: topId }
        break
      }
    }
  } else {
    activeLegendLayer.value = null
  }
}, { deep: true })

const soloLayer = (targetId: string) => {
  Object.keys(opacities.value).forEach(id => {
    opacities.value[id] = 0
  })
  opacities.value[targetId] = 100
}

const setComposite = () => {
  Object.keys(opacities.value).forEach(id => {
    opacities.value[id] = 0
  })
  Object.keys(layerGroups['Adaptive Capacity (Part 3)']).forEach(id => {
    opacities.value[id] = 17
  })
}

let map: maplibregl.Map | null = null

const mapCoordinates = [
  [36.664392580118914, -1.1600389419288961],
  [37.10539577499554, -1.160370141534666],
  [37.10518313059961, -1.4454595549455347],
  [36.66413053825715, -1.445046763546428]
]

onMounted(() => {
  map = new maplibregl.Map({
    container: 'map-container',
    style: 'https://basemaps.cartocdn.com/gl/dark-matter-gl-style/style.json',
    center: [36.75, -1.29], 
    zoom: 10,
    maxBounds: [
      [35.5, -2.2], 
      [38.2, -0.2]  
    ]
  })

  map.on('load', () => {
    Object.values(layerGroups).forEach(group => {
      Object.entries(group).forEach(([id, info]) => {
        map!.addSource(`${id}-source`, {
          type: 'image',
          url: getFile(id, info),
          coordinates: mapCoordinates
        })

        map!.addLayer({
          id: `${id}-layer`,
          type: 'raster',
          source: `${id}-source`,
          paint: {
            'raster-opacity': 0,
            'raster-fade-duration': 300
          }
        })
      })
    })
    
    map!.addSource('nairobi-mask', {
      type: 'geojson',
      data: '/maps/nairobi_mask.geojson'
    })

    map!.addLayer({
      id: 'nairobi-mask-layer',
      type: 'fill',
      source: 'nairobi-mask',
      paint: {
        'fill-color': '#000000',
        'fill-opacity': 1.0
      }
    })
    
    opacities.value['lst_2024'] = 85
  })
})

onUnmounted(() => {
  if (map) map.remove()
})
</script>

<template>
  <div>
    <div id="map-container"></div>

    <div class="sidebar">
      <div class="header">
        <h1>Heat Vulnerability</h1>
        <p>Nairobi Assessment Dashboard</p>
      </div>

      <div class="tabs">
        <button 
          v-for="tab in tabs" 
          :key="tab"
          class="tab-btn"
          :class="{ active: activeTab === tab }"
          @click="activeTab = tab"
        >
          {{ tab.split(' ')[0] }}
        </button>
      </div>

      <div class="layer-group">
        <h2>{{ activeTab }} Maps</h2>
        
        <button 
          v-if="activeTab === 'Adaptive Capacity (Part 3)'"
          class="composite-btn"
          @click="setComposite()"
        >
          Show Composite Index (Equal Weight)
        </button>
        
        <div v-if="Object.keys(layerGroups[activeTab as keyof typeof layerGroups]).length === 0" class="empty-state">
          No maps present yet.
        </div>
        
        <div 
          v-for="(info, id) in layerGroups[activeTab as keyof typeof layerGroups]" 
          :key="id"
          class="layer-card"
          :class="{ active: opacities[id] > 0 }"
        >
          <div class="layer-header">
            <span class="layer-name">{{ info.name }}</span>
            <span class="layer-pct" v-if="opacities[id] > 0" @click="soloLayer(id)">{{ opacities[id] }}%</span>
            <span class="layer-pct off" v-else @click="soloLayer(id)">OFF</span>
          </div>
          <input 
            type="range" 
            min="0" 
            max="100" 
            v-model.number="opacities[id]" 
            class="styled-slider"
          />
        </div>
      </div>
    </div>

    <!-- The Legend -->
    <div v-if="activeLegendLayer" class="legend">
      <div class="legend-title">{{ activeLegendLayer.name }}</div>
      <div class="legend-subtitle">{{ activeLegendLayer.unit }}</div>
      <div class="legend-scale">
        <div class="gradient-bar" :class="{ 'reverse-gradient': activeLegendLayer.id.startsWith('sensitivity') || activeLegendLayer.id.startsWith('lst') }"></div>
        <div class="labels">
          <span>{{ activeLegendLayer.min }}</span>
          <span>{{ activeLegendLayer.max / 2 }}</span>
          <span>{{ activeLegendLayer.max }}+</span>
        </div>
      </div>
    </div>
  </div>
</template>

<style>
/* ... existing styles ... */
#map-container {
  position: absolute;
  top: 0;
  bottom: 0;
  width: 100%;
}

body {
  margin: 0;
  font-family: 'Inter', -apple-system, sans-serif;
  background: #0f172a;
}

.sidebar {
  position: absolute;
  top: 20px;
  left: 20px;
  width: 340px;
  max-height: calc(100vh - 40px);
  z-index: 10;
  background: rgba(30, 41, 59, 0.8);
  backdrop-filter: blur(12px);
  border: 1px solid rgba(255, 255, 255, 0.1);
  border-radius: 16px;
  padding: 24px;
  display: flex;
  flex-direction: column;
  gap: 20px;
  color: white;
  box-shadow: 0 20px 25px -5px rgba(0, 0, 0, 0.3);
}

.header h1 { font-size: 1.4rem; margin: 0; font-weight: 700; background: linear-gradient(to right, #60a5fa, #34d399); -webkit-background-clip: text; -webkit-text-fill-color: transparent; }
.header p { font-size: 0.85rem; color: #94a3b8; margin: 4px 0 0 0; }

.tabs { display: flex; background: rgba(15, 23, 42, 0.5); border-radius: 10px; padding: 4px; }
.tab-btn { flex: 1; border: none; background: transparent; color: #94a3b8; padding: 8px; border-radius: 7px; cursor: pointer; font-size: 0.8rem; font-weight: 600; }
.tab-btn.active { background: #334155; color: white; box-shadow: 0 4px 6px -1px rgba(0,0,0,0.2); }

.layer-group h2 { font-size: 0.75rem; color: #64748b; text-transform: uppercase; letter-spacing: 0.05em; margin-bottom: 12px; }
.layer-card { background: rgba(15, 23, 42, 0.4); border: 1px solid rgba(255, 255, 255, 0.05); padding: 12px; border-radius: 10px; margin-bottom: 8px; }
.layer-card.active { border-color: rgba(59, 130, 246, 0.5); background: rgba(59, 130, 246, 0.05); }
.layer-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px; }
.layer-name { font-size: 0.85rem; font-weight: 500; }
.layer-pct { font-size: 0.7rem; background: #3b82f6; padding: 2px 6px; border-radius: 4px; cursor: pointer; }
.layer-pct.off { background: #334155; color: #94a3b8; }

.styled-slider { -webkit-appearance: none; width: 100%; height: 4px; background: #334155; border-radius: 2px; }
.styled-slider::-webkit-slider-thumb { -webkit-appearance: none; width: 12px; height: 12px; background: #64748b; border-radius: 50%; cursor: pointer; }
.layer-card.active .styled-slider::-webkit-slider-thumb { background: #3b82f6; }

/* Legend Styles */
.legend {
  position: absolute;
  bottom: 30px;
  right: 30px;
  background: rgba(30, 41, 59, 0.9);
  backdrop-filter: blur(8px);
  padding: 16px;
  border-radius: 12px;
  border: 1px solid rgba(255, 255, 255, 0.1);
  color: white;
  width: 200px;
  z-index: 10;
  box-shadow: 0 10px 15px -3px rgba(0, 0, 0, 0.4);
}

.legend-title { font-size: 0.85rem; font-weight: 600; margin-bottom: 2px; }
.legend-subtitle { font-size: 0.7rem; color: #94a3b8; margin-bottom: 12px; }

.legend-scale { display: flex; flex-direction: column; gap: 8px; }
.gradient-bar {
  height: 12px;
  width: 100%;
  border-radius: 4px;
  /* Default: Adaptive Capacity (Red to Green) */
  background: linear-gradient(to right, #d73027, #fc8d59, #fee08b, #d9ef8b, #66bd63, #1a9850);
}

.reverse-gradient {
  /* Sensitivity & Exposure (Blue to Red) */
  background: linear-gradient(to right, #053061, #2166ac, #4393c3, #92c5de, #d1e5f0, #fddbc7, #f4a582, #d6604d, #b2182b, #67001f);
}

.labels {
  display: flex;
  justify-content: space-between;
  font-size: 0.7rem;
  color: #cbd5e1;
  font-family: monospace;
}

.composite-btn { width: 100%; background: #3b82f622; border: 1px solid #3b82f644; color: #60a5fa; padding: 8px; border-radius: 8px; font-size: 0.8rem; cursor: pointer; margin-bottom: 12px; }
.composite-btn:hover { background: #3b82f644; }
</style>
