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
        const height = rect.height || 450;
        const aspect = rect.width / height;
        this.camera = new THREE.PerspectiveCamera(45, aspect, 0.1, 10000);
        this.camera.position.set(100, 100, 100);

        // Renderer with tone mapping for realistic look
        this.renderer = new THREE.WebGLRenderer({
            canvas: this.canvas,
            antialias: true,
        });
        this.renderer.setSize(rect.width, height);
        this.renderer.setPixelRatio(window.devicePixelRatio);
        this.renderer.toneMapping = THREE.ACESFilmicToneMapping;
        this.renderer.toneMappingExposure = 1.6;
        this.renderer.shadowMap.enabled = true;
        this.renderer.shadowMap.type = THREE.PCFSoftShadowMap;

        // Controls
        this.controls = new THREE.OrbitControls(this.camera, this.canvas);
        this.controls.enableDamping = true;
        this.controls.dampingFactor = 0.05;

        // Generate a simple studio environment map for metallic reflections
        this._envMap = this._generateEnvMap();
        this.scene.environment = this._envMap;

        // Hemisphere light (sky/ground) for natural ambient
        const hemiLight = new THREE.HemisphereLight(0xffffff, 0x444466, 1.2);
        this.scene.add(hemiLight);

        // Main directional light (key light) with shadows
        const dirLight1 = new THREE.DirectionalLight(0xffffff, 1.8);
        dirLight1.position.set(150, 250, 150);
        dirLight1.castShadow = true;
        dirLight1.shadow.mapSize.width = 1024;
        dirLight1.shadow.mapSize.height = 1024;
        dirLight1.shadow.camera.near = 1;
        dirLight1.shadow.camera.far = 1000;
        dirLight1.shadow.camera.left = -200;
        dirLight1.shadow.camera.right = 200;
        dirLight1.shadow.camera.top = 200;
        dirLight1.shadow.camera.bottom = -200;
        this.scene.add(dirLight1);

        // Fill light (softer, from opposite side)
        const dirLight2 = new THREE.DirectionalLight(0xaabbdd, 0.8);
        dirLight2.position.set(-100, 50, -100);
        this.scene.add(dirLight2);

        // Rim light from behind for edge definition
        const dirLight3 = new THREE.DirectionalLight(0x6699cc, 0.6);
        dirLight3.position.set(0, -50, -200);
        this.scene.add(dirLight3);

        // Bottom fill to avoid pitch-black undersides
        const dirLight4 = new THREE.DirectionalLight(0x667788, 0.4);
        dirLight4.position.set(50, -150, 50);
        this.scene.add(dirLight4);

        // Grid helper
        const grid = new THREE.GridHelper(200, 20, 0x2a2d3a, 0x1f2230);
        grid.receiveShadow = true;
        this.scene.add(grid);

        // Camera animation target for smooth transitions
        this._cameraTarget = null;
        this._cameraGoal = null;

        // Animate
        this._animate();

        // Resize handler
        window.addEventListener('resize', () => this._onResize());
    }

    /** Generate a procedural environment map for metallic reflections. */
    _generateEnvMap() {
        const pmremGenerator = new THREE.PMREMGenerator(this.renderer);
        pmremGenerator.compileEquirectangularShader();

        // Create a bright studio environment for metallic reflections
        const envScene = new THREE.Scene();
        // Base sky dome — bright neutral gray
        const skyGeo = new THREE.SphereGeometry(500, 16, 8);
        const skyMat = new THREE.MeshBasicMaterial({ color: 0x8899aa, side: THREE.BackSide });
        envScene.add(new THREE.Mesh(skyGeo, skyMat));
        // Gradient bands for subtle variation
        const envColors = [0x6688aa, 0x88aacc, 0xaaccdd, 0xccddee, 0xeef2f6];
        envColors.forEach((color, i) => {
            const geo = new THREE.SphereGeometry(490 - i * 5, 8, 4);
            const mat = new THREE.MeshBasicMaterial({
                color, side: THREE.BackSide, opacity: 0.4 + i * 0.12, transparent: true,
            });
            const mesh = new THREE.Mesh(geo, mat);
            mesh.rotation.y = i * 1.2;
            envScene.add(mesh);
        });
        // Large bright area lights for studio-like reflections
        const addPanel = (x, y, z, size, brightness) => {
            const geo = new THREE.PlaneGeometry(size, size);
            const mat = new THREE.MeshBasicMaterial({ color: brightness, side: THREE.DoubleSide });
            const panel = new THREE.Mesh(geo, mat);
            panel.position.set(x, y, z);
            panel.lookAt(0, 0, 0);
            envScene.add(panel);
        };
        addPanel(0, 350, 200, 400, 0xffffff);   // Top key
        addPanel(-300, 100, 200, 300, 0xddeeff); // Left fill
        addPanel(300, 50, -100, 250, 0xeeeeff);  // Right fill
        addPanel(0, -200, 100, 300, 0x667788);   // Ground bounce

        const envMap = pmremGenerator.fromScene(envScene, 0.04).texture;
        pmremGenerator.dispose();
        return envMap;
    }

    _animate() {
        requestAnimationFrame(() => this._animate());

        // Smooth camera animation
        if (this._cameraGoal) {
            this.camera.position.lerp(this._cameraGoal, 0.08);
            if (this.camera.position.distanceTo(this._cameraGoal) < 0.1) {
                this._cameraGoal = null;
            }
        }
        if (this._cameraTarget) {
            this.controls.target.lerp(this._cameraTarget, 0.08);
            if (this.controls.target.distanceTo(this._cameraTarget) < 0.1) {
                this._cameraTarget = null;
            }
        }

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
        const height = rect.height || 450;
        this.camera.aspect = rect.width / height;
        this.camera.updateProjectionMatrix();
        this.renderer.setSize(rect.width, height);
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
                            // GLB from trimesh may lack normals — compute them for proper shading
                            if (!child.geometry.attributes.normal) {
                                child.geometry.computeVertexNormals();
                            }
                            child.material = this._createMaterial();
                            child.castShadow = true;
                            child.receiveShadow = true;

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
                if (!geometry.attributes.normal) {
                    geometry.computeVertexNormals();
                }
                const material = this._createMaterial();
                this.model = new THREE.Mesh(geometry, material);
                this.model.castShadow = true;
                this.model.receiveShadow = true;
                this._addEdges(this.model);
                this.scene.add(this.model);
                this._fitCamera();
                resolve();
            },
            undefined,
            reject
        );
    }

    /** Shared PBR material for machined metal look. */
    _createMaterial() {
        return new THREE.MeshPhysicalMaterial({
            color: 0xc0ccd4,
            metalness: 0.4,
            roughness: 0.35,
            clearcoat: 0.15,
            clearcoatRoughness: 0.3,
            side: THREE.DoubleSide,
            envMap: this._envMap,
            envMapIntensity: 1.0,
        });
    }

    _addEdges(mesh) {
        // Extract edges at crease angle for CAD-style wireframe overlay
        const edges = new THREE.EdgesGeometry(mesh.geometry, 30);
        const lineMat = new THREE.LineBasicMaterial({
            color: 0x2a3a4a,
            transparent: true,
            opacity: 0.35,
        });
        const lines = new THREE.LineSegments(edges, lineMat);
        // Lines are added as children — they inherit parent transforms automatically
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
            const material = new THREE.MeshStandardMaterial({
                color: color,
                transparent: true,
                opacity: isMatched ? 0.85 : 0.4,
                emissive: color,
                emissiveIntensity: isMatched ? 0.3 : 0.1,
                metalness: 0.2,
                roughness: 0.5,
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
        // Dispose GPU resources to prevent memory leaks
        const dispose = (obj) => {
            if (obj.geometry) obj.geometry.dispose();
            if (obj.material) {
                if (Array.isArray(obj.material)) obj.material.forEach(m => m.dispose());
                else obj.material.dispose();
            }
        };
        if (this.model) {
            this.model.traverse(dispose);
            this.scene.remove(this.model);
            this.model = null;
        }
        if (this.edgeLines) {
            this.scene.remove(this.edgeLines);
            this.edgeLines = null;
        }
        this.markers.forEach(m => {
            dispose(m);
            this.scene.remove(m);
        });
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

            this._cameraGoal = newPos;
            this._cameraTarget = target;
        }
    }
}
