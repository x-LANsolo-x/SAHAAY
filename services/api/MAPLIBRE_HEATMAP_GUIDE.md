# MapLibre GL JS Heatmap Configuration Guide

## Overview

This guide shows how to integrate MapLibre GL JS with SAHAAY analytics API to create interactive heatmaps for:
1. Triage counts by geography
2. Complaint density
3. Outbreak probability (Phase 7.3)

---

## Part 1: Setup MapLibre GL JS

### 1.1 Installation

#### Via CDN (Quick Start)
```html
<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <title>SAHAAY GovSahay Heatmap</title>
    <meta name="viewport" content="width=device-width, initial-scale=1">
    
    <!-- MapLibre GL JS -->
    <link href="https://unpkg.com/maplibre-gl@latest/dist/maplibre-gl.css" rel="stylesheet">
    <script src="https://unpkg.com/maplibre-gl@latest/dist/maplibre-gl.js"></script>
    
    <style>
        body { margin: 0; padding: 0; }
        #map { position: absolute; top: 0; bottom: 0; width: 100%; }
    </style>
</head>
<body>
    <div id="map"></div>
    <script src="heatmap.js"></script>
</body>
</html>
```

#### Via npm (Production)
```bash
npm install maplibre-gl
```

```javascript
import maplibregl from 'maplibre-gl';
import 'maplibre-gl/dist/maplibre-gl.css';
```

### 1.2 geo_cell to Coordinates Mapping

Since SAHAAY uses `geo_cell` (pincode-based), we need a mapping function:

```javascript
// Pincode to approximate lat/lng (India)
const PINCODE_TO_COORDS = {
  // Delhi
  'pincode_110xxx': [28.6139, 77.2090],
  'pincode_110001': [28.6139, 77.2090],
  'pincode_110025': [28.5355, 77.2709],
  
  // Bangalore
  'pincode_560xxx': [12.9716, 77.5946],
  'pincode_560001': [12.9716, 77.5946],
  'pincode_560037': [13.0192, 77.5969],
  
  // Mumbai
  'pincode_400xxx': [19.0760, 72.8777],
  'pincode_400001': [19.0760, 72.8777],
  
  // Kolkata
  'pincode_700xxx': [22.5726, 88.3639],
  'pincode_700001': [22.5726, 88.3639],
  
  // Add more as needed
};

function geoCellToCoords(geoCell) {
  // Try exact match first
  if (PINCODE_TO_COORDS[geoCell]) {
    return PINCODE_TO_COORDS[geoCell];
  }
  
  // Try prefix match (e.g., "pincode_110xxx")
  const prefix = geoCell.substring(0, 12); // "pincode_110x"
  for (const [key, coords] of Object.entries(PINCODE_TO_COORDS)) {
    if (key.startsWith(prefix)) {
      return coords;
    }
  }
  
  // Default to India center
  return [20.5937, 78.9629];
}
```

**Production Enhancement:** Use actual pincode geocoding API or database.

---

## Part 2: Heatmap 1 - Triage Counts by Geography

### 2.1 Fetch Data from API

```javascript
async function fetchTriageHeatmapData(authToken) {
  const response = await fetch(
    'http://api.sahaay.gov.in/dashboard/mv/symptom-heatmap?days=30',
    {
      headers: {
        'Authorization': `Bearer ${authToken}`,
        'Content-Type': 'application/json'
      }
    }
  );
  
  if (!response.ok) {
    throw new Error('Failed to fetch heatmap data');
  }
  
  const result = await response.json();
  return result.data;
}
```

### 2.2 Transform to GeoJSON

```javascript
function transformToGeoJSON(heatmapData) {
  const features = heatmapData.map(point => {
    const [lat, lng] = geoCellToCoords(point.geo_cell);
    
    return {
      type: 'Feature',
      geometry: {
        type: 'Point',
        coordinates: [lng, lat] // Note: [lng, lat] order in GeoJSON
      },
      properties: {
        geo_cell: point.geo_cell,
        event_count: point.event_count,
        symptom_category: point.symptom_category,
        avg_intensity: point.avg_intensity,
        max_intensity: point.max_intensity,
        // For heatmap weight
        weight: point.event_count
      }
    };
  });
  
  return {
    type: 'FeatureCollection',
    features: features
  };
}
```

### 2.3 Create Heatmap Layer

```javascript
async function initializeTriageHeatmap(authToken) {
  // Initialize map
  const map = new maplibregl.Map({
    container: 'map',
    style: 'https://demotiles.maplibre.org/style.json', // Free tiles
    center: [78.9629, 20.5937], // India center
    zoom: 4
  });
  
  map.on('load', async () => {
    // Fetch data
    const heatmapData = await fetchTriageHeatmapData(authToken);
    const geoJSON = transformToGeoJSON(heatmapData);
    
    // Add source
    map.addSource('triage-heatmap', {
      type: 'geojson',
      data: geoJSON
    });
    
    // Add heatmap layer
    map.addLayer({
      id: 'triage-heatmap-layer',
      type: 'heatmap',
      source: 'triage-heatmap',
      maxzoom: 15,
      paint: {
        // Increase weight as event_count increases
        'heatmap-weight': [
          'interpolate',
          ['linear'],
          ['get', 'weight'],
          0, 0,
          100, 1
        ],
        
        // Increase intensity as zoom level increases
        'heatmap-intensity': [
          'interpolate',
          ['linear'],
          ['zoom'],
          0, 1,
          15, 3
        ],
        
        // Color ramp: blue (low) → red (high)
        'heatmap-color': [
          'interpolate',
          ['linear'],
          ['heatmap-density'],
          0, 'rgba(33,102,172,0)',
          0.2, 'rgb(103,169,207)',
          0.4, 'rgb(209,229,240)',
          0.6, 'rgb(253,219,199)',
          0.8, 'rgb(239,138,98)',
          1, 'rgb(178,24,43)'
        ],
        
        // Adjust radius by zoom level
        'heatmap-radius': [
          'interpolate',
          ['linear'],
          ['zoom'],
          0, 2,
          15, 20
        ],
        
        // Transition from heatmap to circle layer by zoom level
        'heatmap-opacity': [
          'interpolate',
          ['linear'],
          ['zoom'],
          7, 1,
          15, 0
        ]
      }
    });
    
    // Add circle layer for high zoom (individual points)
    map.addLayer({
      id: 'triage-points',
      type: 'circle',
      source: 'triage-heatmap',
      minzoom: 10,
      paint: {
        // Size circles by event_count
        'circle-radius': [
          'interpolate',
          ['linear'],
          ['get', 'weight'],
          1, 5,
          50, 15,
          100, 25
        ],
        
        // Color by intensity
        'circle-color': [
          'interpolate',
          ['linear'],
          ['get', 'weight'],
          0, '#2166ac',
          50, '#fee090',
          100, '#d73027'
        ],
        
        'circle-stroke-color': 'white',
        'circle-stroke-width': 1,
        
        // Fade in as heatmap fades out
        'circle-opacity': [
          'interpolate',
          ['linear'],
          ['zoom'],
          7, 0,
          15, 1
        ]
      }
    });
    
    // Add popup on click
    map.on('click', 'triage-points', (e) => {
      const feature = e.features[0];
      const props = feature.properties;
      
      new maplibregl.Popup()
        .setLngLat(feature.geometry.coordinates)
        .setHTML(`
          <h3>${props.geo_cell}</h3>
          <p><strong>Triage Count:</strong> ${props.event_count}</p>
          <p><strong>Category:</strong> ${props.symptom_category}</p>
          <p><strong>Avg Intensity:</strong> ${props.avg_intensity.toFixed(1)}</p>
        `)
        .addTo(map);
    });
    
    // Change cursor on hover
    map.on('mouseenter', 'triage-points', () => {
      map.getCanvas().style.cursor = 'pointer';
    });
    
    map.on('mouseleave', 'triage-points', () => {
      map.getCanvas().style.cursor = '';
    });
  });
  
  return map;
}
```

---

## Part 3: Heatmap 2 - Complaint Density

### 3.1 Fetch Complaint Data

```javascript
async function fetchComplaintHeatmapData(authToken) {
  const response = await fetch(
    'http://api.sahaay.gov.in/dashboard/mv/complaint-categories',
    {
      headers: {
        'Authorization': `Bearer ${authToken}`,
        'Content-Type': 'application/json'
      }
    }
  );
  
  const result = await response.json();
  return result.data;
}
```

### 3.2 Create Complaint Heatmap

```javascript
async function initializeComplaintHeatmap(authToken) {
  const map = new maplibregl.Map({
    container: 'map',
    style: 'https://demotiles.maplibre.org/style.json',
    center: [78.9629, 20.5937],
    zoom: 4
  });
  
  map.on('load', async () => {
    const complaintData = await fetchComplaintHeatmapData(authToken);
    
    // Aggregate by geo_cell (sum all categories)
    const aggregated = {};
    complaintData.forEach(item => {
      if (!aggregated[item.geo_cell]) {
        aggregated[item.geo_cell] = {
          geo_cell: item.geo_cell,
          total_complaints: 0,
          categories: []
        };
      }
      aggregated[item.geo_cell].total_complaints += item.total_complaints;
      aggregated[item.geo_cell].categories.push({
        category: item.category,
        count: item.total_complaints
      });
    });
    
    const geoJSON = transformComplaintsToGeoJSON(Object.values(aggregated));
    
    map.addSource('complaint-heatmap', {
      type: 'geojson',
      data: geoJSON
    });
    
    // Similar heatmap configuration with red color scheme
    map.addLayer({
      id: 'complaint-heatmap-layer',
      type: 'heatmap',
      source: 'complaint-heatmap',
      paint: {
        'heatmap-weight': [
          'interpolate',
          ['linear'],
          ['get', 'weight'],
          0, 0,
          50, 1
        ],
        
        // Red color scheme for complaints (more urgent)
        'heatmap-color': [
          'interpolate',
          ['linear'],
          ['heatmap-density'],
          0, 'rgba(255,255,178,0)',
          0.2, 'rgb(254,204,92)',
          0.4, 'rgb(253,141,60)',
          0.6, 'rgb(240,59,32)',
          0.8, 'rgb(189,0,38)',
          1, 'rgb(128,0,38)'
        ],
        
        'heatmap-radius': [
          'interpolate',
          ['linear'],
          ['zoom'],
          0, 2,
          15, 20
        ]
      }
    });
  });
  
  return map;
}

function transformComplaintsToGeoJSON(aggregatedData) {
  const features = aggregatedData.map(item => {
    const [lat, lng] = geoCellToCoords(item.geo_cell);
    
    return {
      type: 'Feature',
      geometry: {
        type: 'Point',
        coordinates: [lng, lat]
      },
      properties: {
        geo_cell: item.geo_cell,
        total_complaints: item.total_complaints,
        categories: JSON.stringify(item.categories),
        weight: item.total_complaints
      }
    };
  });
  
  return {
    type: 'FeatureCollection',
    features: features
  };
}
```

---

## Part 4: Heatmap 3 - Outbreak Probability (Phase 7.3)

### 4.1 Conceptual Implementation

```javascript
async function fetchOutbreakProbabilityData(authToken) {
  // This endpoint will be implemented in Phase 7.3 (OutbreakSense)
  const response = await fetch(
    'http://api.sahaay.gov.in/dashboard/outbreak-probability',
    {
      headers: {
        'Authorization': `Bearer ${authToken}`,
        'Content-Type': 'application/json'
      }
    }
  );
  
  const result = await response.json();
  return result.predictions; // Array of {geo_cell, probability, risk_level}
}
```

### 4.2 Three-Color Risk Heatmap

```javascript
async function initializeOutbreakHeatmap(authToken) {
  const map = new maplibregl.Map({
    container: 'map',
    style: 'https://demotiles.maplibre.org/style.json',
    center: [78.9629, 20.5937],
    zoom: 4
  });
  
  map.on('load', async () => {
    const outbreakData = await fetchOutbreakProbabilityData(authToken);
    const geoJSON = transformOutbreakToGeoJSON(outbreakData);
    
    map.addSource('outbreak-heatmap', {
      type: 'geojson',
      data: geoJSON
    });
    
    // Use graduated colors based on risk level
    map.addLayer({
      id: 'outbreak-risk-layer',
      type: 'circle',
      source: 'outbreak-heatmap',
      paint: {
        'circle-radius': [
          'interpolate',
          ['linear'],
          ['zoom'],
          4, 10,
          10, 30
        ],
        
        // Three risk levels: Low (green), Medium (yellow), High (red)
        'circle-color': [
          'match',
          ['get', 'risk_level'],
          'low', '#2ecc71',      // Green
          'medium', '#f39c12',   // Yellow/Orange
          'high', '#e74c3c',     // Red
          '#95a5a6' // Default gray
        ],
        
        'circle-opacity': 0.6,
        'circle-stroke-width': 2,
        'circle-stroke-color': '#ffffff'
      }
    });
    
    // Add labels for high-risk areas
    map.addLayer({
      id: 'outbreak-labels',
      type: 'symbol',
      source: 'outbreak-heatmap',
      filter: ['==', ['get', 'risk_level'], 'high'],
      layout: {
        'text-field': ['concat', '⚠️ ', ['get', 'probability'], '%'],
        'text-size': 12,
        'text-offset': [0, 2]
      },
      paint: {
        'text-color': '#e74c3c',
        'text-halo-color': '#ffffff',
        'text-halo-width': 2
      }
    });
  });
  
  return map;
}

function transformOutbreakToGeoJSON(outbreakData) {
  const features = outbreakData.map(item => {
    const [lat, lng] = geoCellToCoords(item.geo_cell);
    
    return {
      type: 'Feature',
      geometry: {
        type: 'Point',
        coordinates: [lng, lat]
      },
      properties: {
        geo_cell: item.geo_cell,
        probability: item.probability, // 0-100
        risk_level: item.risk_level, // 'low', 'medium', 'high'
        weight: item.probability
      }
    };
  });
  
  return {
    type: 'FeatureCollection',
    features: features
  };
}
```

---

## Part 5: Advanced Features

### 5.1 Filters and Controls

```javascript
// Add filter controls
function addHeatmapControls(map) {
  // Time range filter
  const timeRangeSelect = document.getElementById('time-range');
  timeRangeSelect.addEventListener('change', async (e) => {
    const days = e.target.value;
    const newData = await fetchTriageHeatmapData(authToken, days);
    const geoJSON = transformToGeoJSON(newData);
    map.getSource('triage-heatmap').setData(geoJSON);
  });
  
  // Category filter
  const categoryCheckboxes = document.querySelectorAll('.category-filter');
  categoryCheckboxes.forEach(checkbox => {
    checkbox.addEventListener('change', () => {
      const selectedCategories = Array.from(categoryCheckboxes)
        .filter(cb => cb.checked)
        .map(cb => cb.value);
      
      // Update layer filter
      map.setFilter('triage-heatmap-layer', [
        'in',
        ['get', 'symptom_category'],
        ['literal', selectedCategories]
      ]);
    });
  });
}
```

### 5.2 Legend

```html
<div id="legend" style="position: absolute; bottom: 30px; right: 10px; background: white; padding: 10px; border-radius: 3px;">
  <h4>Triage Density</h4>
  <div>
    <span style="background: #2166ac; width: 20px; height: 20px; display: inline-block;"></span> Low (0-20)
  </div>
  <div>
    <span style="background: #fee090; width: 20px; height: 20px; display: inline-block;"></span> Medium (21-50)
  </div>
  <div>
    <span style="background: #d73027; width: 20px; height: 20px; display: inline-block;"></span> High (51+)
  </div>
</div>
```

### 5.3 Auto-Refresh

```javascript
// Refresh heatmap every 15 minutes
function setupAutoRefresh(map, authToken) {
  setInterval(async () => {
    console.log('Refreshing heatmap data...');
    const newData = await fetchTriageHeatmapData(authToken);
    const geoJSON = transformToGeoJSON(newData);
    map.getSource('triage-heatmap').setData(geoJSON);
  }, 15 * 60 * 1000); // 15 minutes
}
```

---

## Part 6: Production Enhancements

### 6.1 Use Real H3 Geo-hashing

```bash
npm install h3-js
```

```javascript
import { geoToH3, h3ToGeoBoundary } from 'h3-js';

// Convert H3 cell to polygon
function h3CellToPolygon(h3Cell) {
  const boundary = h3ToGeoBoundary(h3Cell);
  
  return {
    type: 'Feature',
    geometry: {
      type: 'Polygon',
      coordinates: [boundary.map(coord => [coord[1], coord[0]])]
    },
    properties: {
      h3_cell: h3Cell
    }
  };
}

// Display as polygons instead of points
map.addLayer({
  id: 'h3-hexagons',
  type: 'fill',
  source: 'h3-source',
  paint: {
    'fill-color': [
      'interpolate',
      ['linear'],
      ['get', 'event_count'],
      0, '#2166ac',
      50, '#fee090',
      100, '#d73027'
    ],
    'fill-opacity': 0.6,
    'fill-outline-color': '#ffffff'
  }
});
```

### 6.2 Clustering for Performance

```javascript
map.addSource('clustered-points', {
  type: 'geojson',
  data: geoJSON,
  cluster: true,
  clusterMaxZoom: 14,
  clusterRadius: 50
});

map.addLayer({
  id: 'clusters',
  type: 'circle',
  source: 'clustered-points',
  filter: ['has', 'point_count'],
  paint: {
    'circle-color': [
      'step',
      ['get', 'point_count'],
      '#51bbd6', 100,
      '#f1f075', 750,
      '#f28cb1'
    ],
    'circle-radius': [
      'step',
      ['get', 'point_count'],
      20, 100,
      30, 750,
      40
    ]
  }
});
```

---

## Troubleshooting

### Issue: "No data displayed"
- Check API endpoint returns data: `curl -H "Authorization: Bearer TOKEN" http://api.sahaay.gov.in/dashboard/mv/symptom-heatmap`
- Verify geo_cell coordinates are valid
- Check browser console for errors

### Issue: "Map not rendering"
- Ensure MapLibre CSS is loaded
- Check map container has height: `#map { height: 100vh; }`
- Verify style URL is accessible

### Issue: "Poor performance"
- Enable clustering for large datasets
- Use materialized views (faster queries)
- Consider WebGL heatmap libraries for > 10K points

---

## Complete Example

See `services/api/examples/heatmap-demo.html` for a working demo.

**Next Steps:**
1. Implement pincode geocoding API/database
2. Integrate with Phase 7.3 OutbreakSense
3. Add real-time updates via WebSockets
4. Deploy to GovSahay portal

For Superset integration, see `SUPERSET_DASHBOARD_GUIDE.md`.
