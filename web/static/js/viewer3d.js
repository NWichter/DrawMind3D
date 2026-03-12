/**
 * Three.js 3D Model Viewer with feature highlighting and CAD-style rendering.
 */

class Viewer3D {
    constructor(canvasId) {
        this.canvas = document.getElementById(canvasId);
        this.scene = null;
        this.camera = null;
        this.renderer = null;
        this.controls = null;
        this.model = null;
        this.edgeLines = null;
        this.markers = [];
        this.selectedMarker = null;
        this._matchColors = {};

        this._init();
    }

    _init() {
        // Scene
        this.scene = new THREE.Scene();
        this.scene.background = new THREE.Color(0x1a1d27);

        // Camera
        const rect = this.canvas.parentElement.getBoundingClientRect();
        const aspect = rect.width / 450;
        this.camera = new THREE.PerspectiveCamera(45, aspect, 0.1, 10000);
        this.camera.position.set(100, 100, 100);

        // Renderer with tone mapping for realistic look
        this.renderer = new THREE.WebGLRenderer({
            canvas: this.canvas,
            antialias: true,
        });
        this.renderer.setSize(rect.width, 450);
        this.renderer.setPixelRatio(window.devicePixelRatio);
        this.renderer.toneMapping = THREE.ACESFilmicToneMapping;
        this.renderer.toneMappingExposure = 1.2;

        // Controls
        this.controls = new THREE.OrbitControls(this.camera, this.canvas);
        this.controls.enableDamping = true;
        this.controls.dampingFactor = 0.05;

        // Hemisphere light (sky/ground) for natural ambient
        const hemiLight = new THREE.HemisphereLight(0xddeeff, 0x0d1117, 0.8);
        this.scene.add(hemiLight);

        // Main directional light (key light)
        const dirLight1 = new THREE.DirectionalLight(0xffffff, 1.0);
        dirLight1.position.set(150, 250, 150);
        this.scene.add(dirLight1);

        // Fill light (softer, from opposite side)
        const dirLight2 = new THREE.DirectionalLight(0x8899bb, 0.4);
        dirLight2.position.set(-100, 50, -100);
        this.scene.add(dirLight2);

        // Rim light from behind for edge definition
        const dirLight3 = new THREE.DirectionalLight(0x4488cc, 0.3);
        dirLight3.position.set(0, -50, -200);
        this.scene.add(dirLight3);

        // Grid helper
        const grid = new THREE.GridHelper(200, 20, 0x2a2d3a, 0x1f2230);
        this.scene.add(grid);

        // Animate
        this._animate();

        // Resize handler
        window.addEventListener('resize', () => this._onResize());
    }

    _animate() {
        requestAnimationFrame(() => this._animate());
        this.controls.update();

        // Pulse selected marker
        if (this.selectedMarker) {
            const scale = 1 + 0.3 * Math.sin(Date.now() * 0.005);
            this.selectedMarker.scale.set(scale, scale, scale);
        }

        this.renderer.render(this.scene, this.camera);
    }

    _onResize() {
        const rect = this.canvas.parentElement.getBoundingClientRect();
        this.camera.aspect = rect.width / 450;
        this.camera.updateProjectionMatrix();
        this.renderer.setSize(rect.width, 450);
    }

    async loadModel(url) {
        return new Promise((resolve, reject) => {
            const loader = new THREE.GLTFLoader();
            loader.load(
                url,
                (gltf) => {
                    this.model = gltf.scene;

                    // Apply PBR metallic material for machined-metal look
                    this.model.traverse((child) => {
                        if (child.isMesh) {
                            child.material = new THREE.MeshPhysicalMaterial({
                                color: 0xb0bec5,
                                metalness: 0.6,
                                roughness: 0.35,
                                clearcoat: 0.1,
                                clearcoatRoughness: 0.4,
                                side: THREE.DoubleSide,
                                envMapIntensity: 0.5,
                            });

                            // Add edge lines for CAD wireframe look
                            this._addEdges(child);
                        }
                    });

                    this.scene.add(this.model);
                    this._fitCamera();
                    resolve();
                },
                undefined,
                (error) => {
                    console.warn('GLB load failed, trying STL:', error);
                    this._loadSTL(url.replace('.glb', '.stl'), resolve, reject);
                }
            );
        });
    }

    _loadSTL(url, resolve, reject) {
        const loader = new THREE.STLLoader();
        loader.load(
            url,
            (geometry) => {
                const material = new THREE.MeshPhysicalMaterial({
                    color: 0xb0bec5,
                    metalness: 0.6,
                    roughness: 0.35,
                    clearcoat: 0.1,
                    clearcoatRoughness: 0.4,
                    side: THREE.DoubleSide,
                });
                this.model = new THREE.Mesh(geometry, material);
                this._addEdges(this.model);
                this.scene.add(this.model);
                this._fitCamera();
                resolve();
            },
            undefined,
            reject
        );
    }

    _addEdges(mesh) {
        // Extract edges at crease angle for CAD-style wireframe overlay
        const edges = new THREE.EdgesGeometry(mesh.geometry, 30);
        const lineMat = new THREE.LineBasicMaterial({
            color: 0x3a4a5a,
            transparent: true,
            opacity: 0.5,
        });
        const lines = new THREE.LineSegments(edges, lineMat);
        lines.position.copy(mesh.position);
        lines.rotation.copy(mesh.rotation);
        lines.scale.copy(mesh.scale);
        mesh.add(lines);
    }

    _fitCamera() {
        if (!this.model) return;

        const box = new THREE.Box3().setFromObject(this.model);
        const center = box.getCenter(new THREE.Vector3());
        const size = box.getSize(new THREE.Vector3());
        const maxDim = Math.max(size.x, size.y, size.z);

        this.camera.position.set(
            center.x + maxDim * 1.5,
            center.y + maxDim * 1.0,
            center.z + maxDim * 1.5
        );
        this.controls.target.copy(center);
        this.controls.update();

        // Scale grid to model size
        this.scene.children.forEach(c => {
            if (c.isGridHelper) {
                const gridSize = Math.max(maxDim * 3, 200);
                c.scale.set(gridSize / 200, 1, gridSize / 200);
                c.position.y = box.min.y;
            }
        });
    }

    /**
     * Color palette for matched annotation-feature pairs.
     * Same palette used by PDFViewer for consistent cross-viewer mapping.
     */
    static MATCH_COLORS = [
        0x60a5fa, 0x4ade80, 0xfacc15, 0xf87171,
        0xa78bfa, 0xfb923c, 0x2dd4bf, 0xf472b6,
        0x38bdf8, 0xa3e635, 0xe879f9, 0x22d3ee,
    ];

    addFeatureMarkers(holes, matches) {
        // Remove existing markers
        this.markers.forEach(m => this.scene.remove(m));
        this.markers = [];
        this._matchColors = {};

        // Build match index: feature_id → {match, colorIndex}
        const matchByFeature = {};
        matches.forEach((m, idx) => {
            matchByFeature[m.feature_id] = { match: m, colorIdx: idx };
            this._matchColors[m.feature_id] = idx;
        });

        holes.forEach((hole, index) => {
            const center = hole.center;
            if (!center || center.length < 3) return;

            const matchInfo = matchByFeature[hole.id];
            const isMatched = !!matchInfo;
            const confidence = matchInfo ? matchInfo.match.confidence : 0;
            const colorIdx = matchInfo ? matchInfo.colorIdx : -1;

            // Color: matched pairs get palette color, unmatched get gray
            let color;
            if (!isMatched) {
                color = 0x555555;
            } else {
                color = Viewer3D.MATCH_COLORS[colorIdx % Viewer3D.MATCH_COLORS.length];
            }

            // Ring torus for hole markers (better than sphere for cylindrical features)
            const radius = Math.max(hole.primary_diameter * 0.4, 1.5);
            const geometry = new THREE.TorusGeometry(radius, radius * 0.2, 12, 32);
            const material = new THREE.MeshBasicMaterial({
                color: color,
                transparent: true,
                opacity: isMatched ? 0.85 : 0.4,
            });
            const marker = new THREE.Mesh(geometry, material);
            marker.position.set(center[0], center[1], center[2]);

            // Orient torus along hole axis if available
            if (hole.axis && hole.axis.length === 3) {
                const axis = new THREE.Vector3(hole.axis[0], hole.axis[1], hole.axis[2]).normalize();
                const up = new THREE.Vector3(0, 1, 0);
                const quat = new THREE.Quaternion().setFromUnitVectors(up, axis);
                marker.quaternion.copy(quat);
            }

            marker.userData = {
                holeId: hole.id,
                matchId: matchInfo ? matchInfo.match.id : null,
                index: index,
                colorIdx: colorIdx,
            };

            this.scene.add(marker);
            this.markers.push(marker);
        });
    }

    /** Get the color index assigned to a feature match (for cross-viewer sync). */
    getMatchColorIndex(featureId) {
        return this._matchColors[featureId] ?? -1;
    }

    clearModel() {
        if (this.model) {
            this.scene.remove(this.model);
            this.model = null;
        }
        if (this.edgeLines) {
            this.scene.remove(this.edgeLines);
            this.edgeLines = null;
        }
        this.markers.forEach(m => this.scene.remove(m));
        this.markers = [];
        this.selectedMarker = null;
        this._matchColors = {};
    }

    highlightFeature(holeId) {
        // Reset previous selection
        if (this.selectedMarker) {
            this.selectedMarker.material.opacity = this.selectedMarker.userData.matchId ? 0.85 : 0.4;
            this.selectedMarker.scale.set(1, 1, 1);
        }

        // Find and highlight new marker
        const marker = this.markers.find(m => m.userData.holeId === holeId);
        if (marker) {
            this.selectedMarker = marker;
            marker.material.opacity = 1.0;

            // Smooth camera animation to marker
            const target = marker.position.clone();
            const box = this.model ? new THREE.Box3().setFromObject(this.model) : null;
            const modelSize = box ? box.getSize(new THREE.Vector3()).length() : 100;
            const offset = new THREE.Vector3(
                modelSize * 0.4,
                modelSize * 0.3,
                modelSize * 0.4
            );
            const newPos = target.clone().add(offset);

            this.camera.position.lerp(newPos, 0.3);
            this.controls.target.lerp(target, 0.3);
        }
    }
}
