<script setup lang="ts">
import { onMounted, ref, onUnmounted, watch } from 'vue'
import { Icon } from '@iconify/vue'
import maplibregl from 'maplibre-gl'
import 'maplibre-gl/dist/maplibre-gl.css'

// Our Tab Structure
const tabs = ['Exposure (Part 1)', 'Sensitivity (Part 2)', 'Adaptive Capacity (Part 3)']
const activeTab = ref(tabs[0])

// Day/Night mode
const isDarkMode = ref(false)
const toggleDarkMode = () => {
  isDarkMode.value = !isDarkMode.value
  if (!map) return
  const style = isDarkMode.value ? 'https://basemaps.cartocdn.com/gl/dark-matter-gl-style/style.json' : 'https://basemaps.cartocdn.com/gl/positron-gl-style/style.json'
  map.setStyle(style)
  map.once('style.load', () => {
    loadMapLayers()
  })
}

const useHatch = ref(false)

// Our pre-calculated colored maps
const layerGroups = {
  'Exposure (Part 1)': {
    lst_2020: { name: 'LST 2020', file: '/maps/lst_2020.png', unit: '°C', min: 20, max: 45 },
    lst_2022: { name: 'LST 2022', file: '/maps/lst_2022.png', unit: '°C', min: 20, max: 45 },
    lst_2024: { name: 'LST 2024', file: '/maps/lst_2024.png', unit: '°C', min: 20, max: 45 }
  },
  'Sensitivity (Part 2)': {
    sensitivity_population: { name: 'Total Population (2020)', file: '/maps/sensitivity_population.png', unit: 'People/ha', min: 0, max: 1200 },
    sensitivity_pop_2030: { name: 'Predicted Population (2030)', file: '/maps/sensitivity_pop_2030.png', unit: 'People/ha', min: 0, max: 1200 },
    sensitivity_elderly: { name: 'Elderly Pop (60+, 2020)', file: '/maps/sensitivity_elderly_population.png', unit: 'People/ha', min: 0, max: 150 },
    sensitivity_children: { name: 'Children Pop (<5, 2020)', file: '/maps/sensitivity_children_population.png', unit: 'People/ha', min: 0, max: 200 },
    sensitivity_pop_evolution: { name: 'Pop Growth (2010-2020)', file: '/maps/sensitivity_pop_evolution.png', unit: 'People/ha', min: 0, max: 200 },
    sensitivity_wealth: { name: 'Relative Wealth Index (2021)', file: '/maps/sensitivity_wealth.png', unit: 'Score', min: -1, max: 2 }
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

const getFile = (id: string, info: any) => {
  return info.file
}

// Opacity state for every raster layer (0 to 100)
const opacities = ref<Record<string, number>>({})
Object.entries(layerGroups).forEach(([groupName, group]) => {
  Object.keys(group).forEach(id => {
    opacities.value[id] = 0 // Everything hidden by default
  })
})

// Visibility state for Vector Layers
const vectorLayers = ref({
  'informal-settlements': { id: 'informal-settlements-layer', name: 'Informal Settlements', visible: true, color: '#ef4444' },
  'water-bodies': { id: 'water-bodies-layer', name: 'Water Bodies', visible: false, color: '#3b82f6' },
  'green-spaces': { id: 'green-spaces-layer', name: 'Green Spaces', visible: false, color: '#10b981' }
})


const currentExposureYear = ref('2024')

const setExposureYear = (year: string) => {
  const oldYear = currentExposureYear.value
  currentExposureYear.value = year
  
  const currentOpacity = opacities.value[`lst_${oldYear}`]
  if (currentOpacity > 0) {
    opacities.value[`lst_${oldYear}`] = 0
    opacities.value[`lst_${year}`] = currentOpacity
  }
}


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

watch(vectorLayers, (newVecs) => {
  if (!map || !map.isStyleLoaded()) return
  Object.entries(newVecs).forEach(([key, layer]) => {
    const layerIds = [
      layer.id,
      `${layer.id}-fill`,
      `${layer.id}-hatch`,
      `${layer.id}-line`,
      `${layer.id}-point`,
      `${layer.id}-outline`
    ];
    layerIds.forEach(id => {
      if (map!.getLayer(id)) {
        if (id === 'green-spaces-layer-hatch') {
          map!.setLayoutProperty(id, 'visibility', (layer.visible && useHatch.value) ? 'visible' : 'none')
        } else if (id === 'green-spaces-layer-fill') {
          map!.setLayoutProperty(id, 'visibility', (layer.visible && !useHatch.value) ? 'visible' : 'none')
        } else {
          map!.setLayoutProperty(id, 'visibility', layer.visible ? 'visible' : 'none')
        }
      }
    });
  })
}, { deep: true })

watch(useHatch, (val) => {
  if (!map || !map.isStyleLoaded()) return
  if (map.getLayer('green-spaces-layer-hatch')) {
    map.setLayoutProperty('green-spaces-layer-hatch', 'visibility', (vectorLayers.value['green-spaces'].visible && val) ? 'visible' : 'none')
  }
  if (map.getLayer('green-spaces-layer-fill')) {
    map.setLayoutProperty('green-spaces-layer-fill', 'visibility', (vectorLayers.value['green-spaces'].visible && !val) ? 'visible' : 'none')
  }
})

const soloLayer = (targetId: string) => {
  const isCurrentlyActive = opacities.value[targetId] > 0
  if (!isCurrentlyActive) {
    Object.keys(opacities.value).forEach(id => {
      opacities.value[id] = 0
    })
    opacities.value[targetId] = 100
  } else {
    opacities.value[targetId] = 0
  }
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

const loadMapLayers = () => {
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
            'raster-opacity': opacities.value[id] ? opacities.value[id] / 100 : 0,
            'raster-fade-duration': 300
          }
        })
      })
    })

    // Load new Interactive Vector GeoJSONs
    map!.addSource('informal-settlements-source', { type: 'geojson', data: '/maps/informal_settlements.geojson' })
    // Transparent fill kept ONLY for hover detection (no coloured zone)
    map!.addLayer({
      id: 'informal-settlements-layer',
      type: 'fill',
      source: 'informal-settlements-source',
      paint: { 'fill-color': '#ef4444', 'fill-opacity': 0 },
      layout: { visibility: vectorLayers.value['informal-settlements'].visible ? 'visible' : 'none' }
    })
    // White halo so the border reads on any heatmap background
    map!.addLayer({
      id: 'informal-settlements-layer-outline',
      type: 'line',
      source: 'informal-settlements-source',
      paint: { 'line-color': '#ffffff', 'line-width': 1.5, 'line-opacity': 0.85 },
      layout: { visibility: vectorLayers.value['informal-settlements'].visible ? 'visible' : 'none' }
    })
    // Bold coloured border on top
    map!.addLayer({
      id: 'informal-settlements-layer-line',
      type: 'line',
      source: 'informal-settlements-source',
      paint: { 'line-color': '#00FF00', 'line-width': 1. },
      layout: { visibility: vectorLayers.value['informal-settlements'].visible ? 'visible' : 'none' }
    })


    map!.addSource('water-bodies-source', { type: 'geojson', data: '/maps/water_bodies.geojson' })
    map!.addLayer({
      id: 'water-bodies-layer-fill',
      type: 'fill',
      source: 'water-bodies-source',
      filter: ['==', ['geometry-type'], 'Polygon'],
      paint: { 'fill-color': '#3b82f6', 'fill-opacity': 0.5 },
      layout: { visibility: vectorLayers.value['water-bodies'].visible ? 'visible' : 'none' }
    })
    map!.addLayer({
      id: 'water-bodies-layer-line',
      type: 'line',
      source: 'water-bodies-source',
      filter: ['==', ['geometry-type'], 'LineString'],
      paint: { 'line-color': '#3b82f6', 'line-width': 2, 'line-opacity': 0.8 },
      layout: { visibility: vectorLayers.value['water-bodies'].visible ? 'visible' : 'none' }
    })

    // Green Spaces (SVG Hatch & Fill)
    const svgHatch = `<svg width="10" height="10" viewBox="0 0 10 10" xmlns="http://www.w3.org/2000/svg"><path d="M-2,2 l4,-4 M0,10 l10,-10 M8,12 l4,-4" stroke="#22c55e" stroke-width="1.5" fill="none"/></svg>`;
    const img = new Image(10, 10);
    img.onload = () => {
        if (!map!.hasImage('hatch-pattern')) map!.addImage('hatch-pattern', img);
        map!.addSource('green-spaces-source', { type: 'geojson', data: '/maps/green_spaces.geojson' })
        map!.addLayer({
          id: 'green-spaces-layer-fill',
          type: 'fill',
          source: 'green-spaces-source',
          paint: { 'fill-color': '#22c55e', 'fill-opacity': 0.3 },
          layout: { visibility: (vectorLayers.value['green-spaces'].visible && !useHatch.value) ? 'visible' : 'none' }
        }, 'nairobi-mask-layer') // Put before mask to prevent overflowing borders
        
        map!.addLayer({
          id: 'green-spaces-layer-hatch',
          type: 'fill',
          source: 'green-spaces-source',
          paint: { 'fill-pattern': 'hatch-pattern', 'fill-opacity': 0.8 },
          layout: { visibility: (vectorLayers.value['green-spaces'].visible && useHatch.value) ? 'visible' : 'none' }
        }, 'nairobi-mask-layer')
        
        map!.addLayer({
          id: 'green-spaces-layer-outline',
          type: 'line',
          source: 'green-spaces-source',
          paint: { 'line-color': '#166534', 'line-width': 1 },
          layout: { visibility: vectorLayers.value['green-spaces'].visible ? 'visible' : 'none' }
        }, 'nairobi-mask-layer')
    };
    img.src = 'data:image/svg+xml;base64,' + btoa(svgHatch);
    
    map!.addSource('hover-grid-source', { type: 'geojson', data: '/maps/hover_grid.geojson' })
    map!.addLayer({
      id: 'hover-grid-layer',
      type: 'fill',
      source: 'hover-grid-source',
      paint: { 'fill-opacity': 0 }
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
        'fill-color': isDarkMode.value ? '#000000' : '#ffffff',
        'fill-opacity': 1.0
      }
    })
}

onMounted(() => {
  map = new maplibregl.Map({
    container: 'map-container',
    style: isDarkMode.value ? 'https://basemaps.cartocdn.com/gl/dark-matter-gl-style/style.json' : 'https://basemaps.cartocdn.com/gl/positron-gl-style/style.json',
    center: [36.75, -1.29], 
    zoom: 10,
    maxBounds: [
      [35.5, -2.2], 
      [38.2, -0.2]  
    ]
  })

  map.on('load', () => {
    loadMapLayers()
    
    // Interaction Logic
    const popup = new maplibregl.Popup({
        closeButton: false,
        closeOnClick: false,
        className: 'custom-popup'
    });

    const interactiveLayers = [
        'informal-settlements-layer',
        'water-bodies-layer-fill', 
        'water-bodies-layer-line', 
        'green-spaces-layer-hatch',
        'green-spaces-layer-fill', 
        'hover-grid-layer'
    ];
    
    map!.on('mousemove', (e) => {
        const features = map!.queryRenderedFeatures(e.point, { layers: interactiveLayers });
        
        if (features.length === 0) {
            map!.getCanvas().style.cursor = '';
            popup.remove();
            return;
        }

        map!.getCanvas().style.cursor = 'pointer';
        let html = '';
        const foundTypes = new Set();
        
        // Raster Data (Hover Grid)
        const gridFeature = features.find(f => f.layer.id === 'hover-grid-layer');
        if (gridFeature && activeLegendLayer.value) {
            const props = gridFeature.properties;
            let val = null;
            if (activeLegendLayer.value.id === 'lst_2020') val = props.lst_2020;
            else if (activeLegendLayer.value.id === 'lst_2022') val = props.lst_2022;
            else if (activeLegendLayer.value.id === 'lst_2024') val = props.lst_2024;
            else if (activeLegendLayer.value.id === 'sensitivity_population') val = props.pop_total;
            else if (activeLegendLayer.value.id === 'sensitivity_pop_2030') val = "Data from WorldPop";
            else if (activeLegendLayer.value.id === 'sensitivity_children') val = props.pop_children;
            else if (activeLegendLayer.value.id === 'sensitivity_elderly') val = props.pop_elderly;
            else if (activeLegendLayer.value.id === 'sensitivity_pop_evolution') val = "Data from WorldPop";
            else if (activeLegendLayer.value.id === 'sensitivity_wealth') val = "Data from Meta HDX";
            
            if (val !== null && val !== undefined) {
                html += `<div style="margin-bottom: 6px; padding-bottom: 6px; border-bottom: 1px solid rgba(150,150,150,0.2);">
                            <strong>${activeLegendLayer.value.name}</strong><br/>
                            <span style="font-size: 1.1rem; color: #facc15; font-weight: 600;">${val} ${activeLegendLayer.value.unit}</span>
                         </div>`;
            }
        }

        // Vector Data
        const vectorFeatures = features.filter(f => f.layer.id !== 'hover-grid-layer');
        if (vectorFeatures.length > 0) {
            html += '<div style="display:flex; flex-direction:column; gap:4px;">';
            vectorFeatures.forEach(f => {
               const l = f.layer.id;
               if (l === 'informal-settlements-layer' && !foundTypes.has('informal')) {
                   const areaHa = (f.properties?.area_m2 ?? 0) / 10000
                   html += `<div><span style="color:#ef4444; font-weight: 500;">◼ Informal Settlement</span>`
                   if (areaHa > 0) html += `<br/><span style="font-size:0.75rem; color:var(--text-secondary);">Area: ${areaHa.toFixed(1)} ha</span>`
                   html += `</div>`
                   foundTypes.add('informal');
               } else if (l.startsWith('water-bodies-layer') && !foundTypes.has('water')) {
                   html += `<div><span style="color:#3b82f6; font-weight: 500;">◼ Water Body</span></div>`;
                   foundTypes.add('water');
               } else if (l.startsWith('green-spaces-layer') && !foundTypes.has('green')) {
                   html += `<div><span style="color:#10b981; font-weight: 500;">◼ Green Space</span></div>`;
                   foundTypes.add('green');
               }
            });
            html += '</div>';
        }
        
        if (html) {
           popup.setLngLat(e.lngLat).setHTML(html).addTo(map!);
        } else {
           popup.remove();
        }
    });

    opacities.value['lst_2024'] = 85
  })
})

onUnmounted(() => {
  if (map) map.remove()
})
</script>

<template>
  <div :class="isDarkMode ? 'theme-dark' : 'theme-light'" class="app-wrapper">
    <div id="map-container"></div>

    <div class="sidebar">
      <div class="sidebar-content">
        <div class="header">
          <div style="display: flex; justify-content: space-between; align-items: flex-start;">
            <div>
              <h1>Heat Vulnerability</h1>
              <p>Nairobi Assessment Dashboard</p>
            </div>
            <button @click="toggleDarkMode" class="theme-toggle" title="Toggle Theme">
              <Icon icon="line-md:light-dark" style="font-size: 1.25rem;" />
            </button>
          </div>
        </div>
        <!-- Vector Interactivity Toggles -->
        <div class="layer-group vector-section">
          <h2 style="display: flex; justify-content: space-between; align-items: center;">
            Interactive Ground Truth
          </h2>
          <div class="vector-switches">
            <template v-for="(layer, key) in vectorLayers" :key="key">
              <label class="switch-label">
                <input type="checkbox" v-model="layer.visible" />
                <span class="custom-checkbox" :style="{ '--active-color': layer.color }"></span>
                <span style="flex-grow: 1">{{ layer.name }}</span>
                <button v-if="key === 'green-spaces'" @click.stop.prevent="useHatch = !useHatch" class="hatch-btn">
                  {{ useHatch ? 'Hatch' : 'Solid' }}
                </button>
              </label>
              

            </template>
          </div>
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
          <p class="raster-notice">Note: These raster heatmaps do not display hover info. Use the opacity sliders to visualize trends.</p>
          
          <button 
            v-if="activeTab === 'Adaptive Capacity (Part 3)'"
            class="composite-btn"
            @click="setComposite()"
          >
            Show Composite Index (Equal Weight)
          </button>
          
          <div v-if="activeTab === 'Exposure (Part 1)'" style="display:flex; gap:8px; margin-bottom:12px; background:var(--card-bg); padding:4px; border-radius:10px; border:1px solid var(--border-color);">
            <button v-for="year in ['2020', '2022', '2024']" :key="year"
              class="tab-btn"
              :class="{ active: currentExposureYear === year }"
              @click="setExposureYear(year)"
            >
              {{ year }}
            </button>
          </div>
          
          <div v-if="Object.keys(layerGroups[activeTab as keyof typeof layerGroups]).length === 0" class="empty-state">
            No maps present yet.
          </div>
          
          <template v-for="(info, id) in layerGroups[activeTab as keyof typeof layerGroups]" :key="id">
            <div 
              v-if="!id.startsWith('lst_') || id === 'lst_' + currentExposureYear"
              class="layer-card"
              :class="{ active: opacities[id] > 0 }"
            >
              <div class="layer-header">
                <span class="layer-name">{{ id.startsWith('lst_') ? 'Land Surface Temperature' : info.name }}</span>
                <span class="layer-pct" v-if="opacities[id] > 0" @click="soloLayer(id as string)">{{ opacities[id] }}%</span>
                <span class="layer-pct off" v-else @click="soloLayer(id as string)">OFF</span>
              </div>
              <input 
                type="range" 
                min="0" 
                max="100" 
                v-model.number="opacities[id]" 
                class="styled-slider"
              />
            </div>
          </template>
        </div>
      </div>
    </div>

    <!-- The Legend -->
    <div v-if="activeLegendLayer" class="legend">
      <div class="legend-title">{{ activeLegendLayer.name }}</div>
      <div class="legend-subtitle">{{ activeLegendLayer.unit }}</div>
      <div class="legend-scale">
        <div class="gradient-bar" :class="{
          'reverse-gradient': activeLegendLayer.id.startsWith('lst') || activeLegendLayer.id === 'sensitivity_wealth',
          'seq-gradient': activeLegendLayer.id.startsWith('sensitivity') && activeLegendLayer.id !== 'sensitivity_wealth'
        }"></div>
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
@import url('https://fonts.googleapis.com/css2?family=Host+Grotesk:wght@300;400;500;600;700;800&display=swap');

.app-wrapper {
  position: absolute;
  top: 0; left: 0; right: 0; bottom: 0;
  --bg-color: #f8f9fa;
  --sidebar-bg: rgba(255, 255, 255, 0.85);
  --text-primary: #0f172a;
  --text-secondary: #64748b;
  --border-color: rgba(0, 0, 0, 0.05);
  --card-bg: rgba(255, 255, 255, 0.6);
  --card-active-bg: rgba(59, 130, 246, 0.05);
  --card-active-border: rgba(59, 130, 246, 0.4);
  --slider-bg: #e2e8f0;
  --pct-off-bg: #e2e8f0;
  --shadow: 0 10px 25px -5px rgba(0, 0, 0, 0.1);
}

.theme-dark {
  --bg-color: #0f172a;
  --sidebar-bg: rgba(30, 41, 59, 0.85);
  --text-primary: #f8fafc;
  --text-secondary: #94a3b8;
  --border-color: rgba(255, 255, 255, 0.1);
  --card-bg: rgba(15, 23, 42, 0.6);
  --card-active-bg: rgba(59, 130, 246, 0.1);
  --card-active-border: rgba(59, 130, 246, 0.6);
  --slider-bg: #334155;
  --pct-off-bg: #334155;
  --shadow: 0 20px 25px -5px rgba(0, 0, 0, 0.5);
}

body {
  margin: 0;
  font-family: 'Host Grotesk', -apple-system, sans-serif;
  background: var(--bg-color);
  color: var(--text-primary);
}

#map-container {
  position: absolute;
  top: 0;
  bottom: 0;
  width: 100%;
}

.sidebar {
  position: absolute;
  top: 20px;
  left: 20px;
  width: 340px;
  max-height: calc(100vh - 40px);
  overflow-y: auto;
  z-index: 10;
  background: var(--sidebar-bg);
  backdrop-filter: blur(16px);
  -webkit-backdrop-filter: blur(16px);
  border: 1px solid var(--border-color);
  border-radius: 16px;
  overflow: hidden;
  padding: 0;
  display: flex;
  flex-direction: column;
  color: var(--text-primary);
  box-shadow: var(--shadow);
}
.sidebar-content {
  padding: 24px;
  overflow-y: auto;
  display: flex;
  flex-direction: column;
  gap: 20px;
}
.sidebar-content::-webkit-scrollbar { width: 6px; }
.sidebar-content::-webkit-scrollbar-thumb { background: rgba(150,150,150,0.2); border-radius: 4px; }

.header h1 { 
  font-size: 1.5rem; 
  margin: 0; 
  font-weight: 800; 
  color: var(--text-primary);
  letter-spacing: -0.02em; 
}
.header p { font-size: 0.85rem; color: var(--text-secondary); margin: 4px 0 0 0; font-weight: 400; }

.theme-toggle {
  background: transparent;
  border: 1px solid var(--border-color);
  color: var(--text-primary);
  font-size: 1rem;
  cursor: pointer;
  padding: 6px;
  border-radius: 8px;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: all 0.2s;
}
.theme-toggle:hover {
  background: var(--card-bg);
}

.tabs { display: flex; background: rgba(0, 0, 0, 0.05); border-radius: 10px; padding: 4px; }
.theme-dark .tabs { background: rgba(0, 0, 0, 0.2); }
.tab-btn { flex: 1; border: none; background: transparent; color: var(--text-secondary); padding: 8px; border-radius: 7px; cursor: pointer; font-size: 0.8rem; font-weight: 600; font-family: 'Host Grotesk'; }
.tab-btn.active { background: var(--sidebar-bg); color: var(--text-primary); box-shadow: 0 4px 6px -1px rgba(0,0,0,0.05); }

.layer-group h2 { font-size: 0.75rem; color: var(--text-secondary); text-transform: uppercase; letter-spacing: 0.05em; margin-bottom: 8px; font-weight: 700; }
.raster-notice { font-size: 0.7rem; color: #d97706; margin-top: 0; margin-bottom: 12px; font-style: italic; opacity: 0.9; }
.theme-dark .raster-notice { color: #fbbf24; }

.layer-card { background: var(--card-bg); border: 1px solid var(--border-color); padding: 12px; border-radius: 10px; margin-bottom: 8px; transition: all 0.2s; }
.layer-card.active { border-color: var(--card-active-border); background: var(--card-active-bg); }
.layer-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px; }
.layer-name { font-size: 0.85rem; font-weight: 600; }
.layer-pct { font-size: 0.7rem; background: #3b82f6; color: white; padding: 2px 6px; border-radius: 4px; cursor: pointer; font-weight: 600; }
.layer-pct.off { background: var(--pct-off-bg); color: var(--text-secondary); }

.styled-slider { -webkit-appearance: none; width: 100%; height: 4px; background: var(--slider-bg); border-radius: 2px; }
.styled-slider::-webkit-slider-thumb { -webkit-appearance: none; width: 12px; height: 12px; background: var(--text-secondary); border-radius: 50%; cursor: pointer; }
.layer-card.active .styled-slider::-webkit-slider-thumb { background: #3b82f6; }

/* Vector Section */
.vector-section { background: var(--card-bg); padding: 14px; border-radius: 10px; border: 1px dashed var(--border-color); }
.vector-switches { display: flex; flex-direction: column; gap: 8px; }
.switch-label { display: flex; align-items: center; gap: 10px; font-size: 0.8rem; cursor: pointer; font-weight: 500; }
.switch-label input { display: none; }
.custom-checkbox { width: 16px; height: 16px; border: 2px solid var(--text-secondary); border-radius: 4px; position: relative; transition: all 0.2s; flex-shrink: 0; }
.switch-label input:checked + .custom-checkbox { background: var(--active-color); border-color: var(--active-color); }
.switch-label input:checked + .custom-checkbox::after { content: ''; position: absolute; left: 4px; top: 1px; width: 4px; height: 8px; border: solid white; border-width: 0 2px 2px 0; transform: rotate(45deg); }
.hatch-btn { background: rgba(16, 185, 129, 0.1); border: 1px solid rgba(16, 185, 129, 0.3); color: #059669; padding: 2px 6px; border-radius: 4px; font-size: 0.65rem; cursor: pointer; }
.theme-dark .hatch-btn { color: #34d399; }
.hover-tip { font-size: 0.65rem; background: rgba(16, 185, 129, 0.1); color: #059669; padding: 2px 6px; border-radius: 12px; border: 1px solid rgba(16, 185, 129, 0.2); cursor: help; }
.theme-dark .hover-tip { color: #34d399; }

/* Custom Popup MapLibre */
.custom-popup .maplibregl-popup-content {
  background: var(--sidebar-bg);
  color: var(--text-primary);
  border-radius: 12px;
  border: 1px solid var(--border-color);
  padding: 14px 18px;
  font-family: 'Host Grotesk', sans-serif;
  font-size: 0.85rem;
  backdrop-filter: blur(12px);
  -webkit-backdrop-filter: blur(12px);
  box-shadow: var(--shadow);
}
.custom-popup .maplibregl-popup-tip {
  border-top-color: var(--sidebar-bg);
}

/* Legend Styles */
.legend {
  position: absolute;
  bottom: 30px;
  right: 30px;
  background: var(--sidebar-bg);
  backdrop-filter: blur(12px);
  -webkit-backdrop-filter: blur(12px);
  padding: 16px;
  border-radius: 16px;
  border: 1px solid var(--border-color);
  color: var(--text-primary);
  width: 200px;
  z-index: 10;
  box-shadow: var(--shadow);
}

.legend-title { font-size: 0.85rem; font-weight: 600; margin-bottom: 2px; }
.legend-subtitle { font-size: 0.7rem; color: #64748b; margin-bottom: 12px; }

.legend-scale { display: flex; flex-direction: column; gap: 8px; }
.gradient-bar {
  height: 12px;
  width: 100%;
  border-radius: 4px;
  background: linear-gradient(to right, #d73027, #fc8d59, #fee08b, #d9ef8b, #66bd63, #1a9850);
}

.reverse-gradient {
  background: linear-gradient(to right, #053061, #2166ac, #4393c3, #92c5de, #d1e5f0, #fddbc7, #f4a582, #d6604d, #b2182b, #67001f);
}

/* Sequential (classic) scale for population density layers */
.seq-gradient {
  background: linear-gradient(to right, #ffffcc, #fed976, #feb24c, #fd8d3c, #f03b20, #bd0026);
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
