document.addEventListener('DOMContentLoaded', () => {
    let cy = null;

    // ── Tree state tracking ──────────────────────────
    // Map: nodeId -> [directChildNodeIds]
    const nodeChildren = new Map();
    // Set of nodeIds that are currently expanded
    const expandedNodes = new Set();
    // Node types that can be expanded
    const EXPANDABLE_TYPES = new Set(['Law', 'LawVersion', 'ArticleVersion', 'Paragraph']);

    // ── Cytoscape stylesheet ─────────────────────────
    const STYLE = [
        {
            selector: 'node',
            style: {
                'label': 'data(label)',
                'text-valign': 'center',
                'text-halign': 'center',
                'color': '#ffffff',
                'font-family': 'Cairo, sans-serif',
                'font-size': '11px',
                'font-weight': 'bold',
                'text-wrap': 'wrap',
                'text-max-width': '70px',
                'background-color': '#607d8b',
                'width': '64px',
                'height': '64px',
                'border-width': '2px',
                'border-color': 'rgba(255,255,255,0.15)',
                'overlay-padding': '6px',
                'transition-property': 'background-color, border-color, width, height',
                'transition-duration': '0.25s',
            }
        },
        // Law — large hexagon, teal glow
        {
            selector: 'node[type="Law"]',
            style: {
                'background-color': '#ff5722',
                'shape': 'hexagon',
                'width': '90px',
                'height': '90px',
                'border-color': '#ff8a65',
                'border-width': '3px',
                'font-size': '12px',
            }
        },
        // LawVersion — rounded rectangle, cyan
        {
            selector: 'node[type="LawVersion"]',
            style: {
                'background-color': '#00bcd4',
                'color': '#003740',
                'shape': 'round-rectangle',
                'width': '80px',
                'height': '52px',
                'border-color': '#4dd0e1',
                'font-size': '11px',
            }
        },
        // ArticleVersion — circle, blue
        {
            selector: 'node[type="ArticleVersion"]',
            style: {
                'background-color': '#1565c0',
                'shape': 'ellipse',
                'width': '56px',
                'height': '56px',
                'border-color': '#42a5f5',
                'font-size': '10px',
            }
        },
        // Paragraph — diamond, green
        {
            selector: 'node[type="Paragraph"]',
            style: {
                'background-color': '#2e7d32',
                'shape': 'diamond',
                'width': '52px',
                'height': '52px',
                'border-color': '#66bb6a',
                'font-size': '11px',
            }
        },
        // Item — small pentagon, purple
        {
            selector: 'node[type="Item"]',
            style: {
                'background-color': '#6a1b9a',
                'shape': 'pentagon',
                'width': '46px',
                'height': '46px',
                'border-color': '#ba68c8',
                'font-size': '10px',
            }
        },
        // Judgment — star, gold
        {
            selector: 'node[type="Judgment"]',
            style: {
                'background-color': '#f57f17',
                'shape': 'star',
                'width': '62px',
                'height': '62px',
                'border-color': '#ffee58',
                'border-width': '3px',
                'font-size': '10px',
                'color': '#fff8e1',
            }
        },

        // Expanded node — glowing border
        {
            selector: 'node.expanded',
            style: {
                'border-width': '3px',
                'border-color': '#66fcf1',
                'shadow-blur': '20px',
                'shadow-color': '#66fcf1',
                'shadow-opacity': 0.6,
                'shadow-offset-x': 0,
                'shadow-offset-y': 0,
            }
        },

        // Selected node highlight
        {
            selector: 'node:selected',
            style: {
                'border-width': '4px',
                'border-color': '#ffffff',
            }
        },

        // Edges
        {
            selector: 'edge',
            style: {
                'width': 2,
                'line-color': 'rgba(255,255,255,0.2)',
                'target-arrow-color': 'rgba(255,255,255,0.2)',
                'target-arrow-shape': 'triangle',
                'curve-style': 'bezier',
                'label': 'data(label)',
                'font-size': '9px',
                'color': '#90a4ae',
                'text-background-opacity': 0.7,
                'text-background-color': '#0b0c10',
                'text-background-padding': '2px',
                'font-family': 'Outfit, sans-serif',
            }
        },
        {
            selector: 'edge[label="CITES"]',
            style: {
                'line-color': '#f57f17',
                'target-arrow-color': '#f57f17',
                'line-style': 'dashed',
                'width': 2.5,
            }
        },
        {
            selector: 'edge[label="REPLACES_VERSION"]',
            style: {
                'line-color': '#e91e63',
                'target-arrow-color': '#e91e63',
            }
        },
        {
            selector: 'edge[label="HAS_VERSION"]',
            style: {
                'line-color': '#00bcd4',
                'target-arrow-color': '#00bcd4',
                'width': 2.5,
            }
        },
        {
            selector: 'edge[label="HAS_ARTICLE"]',
            style: {
                'line-color': '#1565c0',
                'target-arrow-color': '#1565c0',
            }
        },
        {
            selector: 'edge[label="HAS_PARAGRAPH"]',
            style: {
                'line-color': '#2e7d32',
                'target-arrow-color': '#2e7d32',
            }
        },
        {
            selector: 'edge[label="HAS_ITEM"]',
            style: {
                'line-color': '#6a1b9a',
                'target-arrow-color': '#6a1b9a',
            }
        },
    ];

    // ── Init Cytoscape ────────────────────────────────
    function initCytoscape() {
        cy = cytoscape({
            container: document.getElementById('cy'),
            elements: [],
            style: STYLE,
            layout: { name: 'preset' },
            minZoom: 0.1,
            maxZoom: 4,
        });

        cy.on('tap', 'node', handleNodeTap);
    }

    // ── Tap handler ───────────────────────────────────
    async function handleNodeTap(evt) {
        const node = evt.target;
        const data = node.data();

        // Show detail panel
        showNodeDetails(data);

        if (!EXPANDABLE_TYPES.has(data.type)) return;

        const nid = data.id;

        if (expandedNodes.has(nid)) {
            collapseNode(nid);
            node.removeClass('expanded');
        } else {
            await expandNode(node, data);
        }
    }

    // ── Expand ────────────────────────────────────────
    async function expandNode(node, data) {
        const nid = data.id;
        const url = `/api/graph/children?node_id=${encodeURIComponent(nid)}&node_type=${encodeURIComponent(data.type)}`;

        try {
            showToast('جاري تحميل البيانات...');
            const res = await fetch(url);
            const result = await res.json();

            if (!result.nodes || result.nodes.length === 0) {
                showToast('لا توجد عناصر فرعية لهذا النود');
                return;
            }

            // Filter out already-present nodes/edges
            const newNodes = result.nodes.filter(n => !cy.getElementById(n.data.id).length);
            const newEdges = result.edges.filter(e => !cy.getElementById(e.data.id).length);

            if (newNodes.length === 0) {
                showToast('العناصر الفرعية موجودة بالفعل');
                return;
            }

            // Lock existing nodes so layout only moves new ones
            cy.nodes().lock();

            // Add new elements
            cy.add([...newNodes, ...newEdges]);

            // Track children
            const childIds = result.nodes.map(n => n.data.id);
            nodeChildren.set(nid, childIds);
            expandedNodes.add(nid);
            node.addClass('expanded');

            // Unlock and animate layout
            cy.nodes().unlock();
            cy.nodes().lock();

            // Let new nodes move freely
            newNodes.forEach(n => {
                cy.getElementById(n.data.id).unlock();
            });

            const layoutOptions = getLayoutOptions(newNodes.length);
            cy.layout(layoutOptions).run();

            setTimeout(() => {
                cy.nodes().unlock();
                showToast(`تم تحميل ${newNodes.length} عنصر`);
            }, layoutOptions.animationDuration + 100);

        } catch (err) {
            cy.nodes().unlock();
            console.error(err);
            showToast('حدث خطأ أثناء تحميل البيانات');
        }
    }

    function getLayoutOptions(newCount) {
        // For small expansions use cose; for large use grid
        if (newCount <= 8) {
            return {
                name: 'cose',
                animate: true,
                animationDuration: 600,
                fit: false,
                nodeRepulsion: 500000,
                idealEdgeLength: 130,
                nodeOverlap: 10,
                componentSpacing: 80,
                gravity: 40,
            };
        }
        return {
            name: 'cose',
            animate: true,
            animationDuration: 800,
            fit: false,
            nodeRepulsion: 800000,
            idealEdgeLength: 90,
            nodeOverlap: 5,
            componentSpacing: 50,
            gravity: 20,
        };
    }

    // ── Collapse ──────────────────────────────────────
    function getAllDescendants(nid) {
        const desc = new Set();
        const queue = [nid];
        while (queue.length) {
            const cur = queue.shift();
            const children = nodeChildren.get(cur) || [];
            for (const cid of children) {
                if (!desc.has(cid)) {
                    desc.add(cid);
                    queue.push(cid);
                }
            }
        }
        return desc;
    }

    function collapseNode(nid) {
        const descendants = getAllDescendants(nid);
        cy.batch(() => {
            descendants.forEach(id => {
                cy.remove(cy.getElementById(id));
                nodeChildren.delete(id);
                expandedNodes.delete(id);
            });
        });
        nodeChildren.delete(nid);
        expandedNodes.delete(nid);
    }

    // ── Load Laws (root nodes) ────────────────────────
    async function loadLaws() {
        try {
            const res = await fetch('/api/graph/laws');
            const data = await res.json();

            if (!data.nodes || data.nodes.length === 0) {
                showToast('لا توجد بيانات. اضغط "قراءة المستندات" أولاً.');
                return;
            }

            cy.add(data.nodes);

            // Center the law node(s)
            const cx = cy.container().offsetWidth / 2;
            const cy_h = cy.container().offsetHeight / 2;
            const count = data.nodes.length;

            data.nodes.forEach((n, i) => {
                const node = cy.getElementById(n.data.id);
                const angle = count > 1 ? (2 * Math.PI * i / count) - Math.PI / 2 : 0;
                const r = count > 1 ? 160 : 0;
                node.position({ x: cx + r * Math.cos(angle), y: cy_h + r * Math.sin(angle) });
            });

            cy.fit(cy.nodes(), 120);
            showToast(`تم تحميل ${count} قانون — اضغط على القانون لفتح نسخه`);

        } catch (err) {
            console.error(err);
            showToast('تعذّر الاتصال بقاعدة البيانات');
        }
    }

    // ── Detail Panel ──────────────────────────────────
    function showNodeDetails(nodeData) {
        document.getElementById('detail-fallback').classList.add('hidden');
        const contentDiv = document.getElementById('detail-content');
        contentDiv.classList.remove('hidden');

        const badge = document.getElementById('detail-type');
        const title = document.getElementById('detail-title');
        const body  = document.getElementById('detail-text');
        const meta  = document.getElementById('detail-meta-json');

        badge.innerText = translateType(nodeData.type);
        badge.style.backgroundColor = getTypeColor(nodeData.type);
        title.innerText = nodeData.label;

        // Use rich text or full_text
        const props = nodeData.properties || {};
        const textVal = nodeData.text || props.text || props.full_text || props.title || 'لا يوجد نص لهذا العنصر.';
        body.innerText = textVal;

        // Meta: exclude heavy text fields
        const metaProps = { ...props };
        delete metaProps.text;
        delete metaProps.full_text;
        meta.innerText = JSON.stringify(metaProps, null, 2);

        // Expand/collapse hint
        const hint = document.getElementById('expand-hint');
        if (hint) {
            if (EXPANDABLE_TYPES.has(nodeData.type)) {
                const isExpanded = expandedNodes.has(nodeData.id);
                hint.innerText = isExpanded ? '🔼 اضغط مرة أخرى لإغلاق الفروع' : '🔽 اضغط على النود في الرسم لفتح الفروع';
                hint.classList.remove('hidden');
            } else {
                hint.classList.add('hidden');
            }
        }
    }

    function translateType(type) {
        return {
            'Law': 'قانون رئيسي',
            'LawVersion': 'نسخة القانون',
            'ArticleVersion': 'مادة قانونية',
            'Paragraph': 'فقرة فرعية',
            'Item': 'بند فرعي',
            'Judgment': 'حكم قضائي',
        }[type] || type;
    }

    function getTypeColor(type) {
        return {
            'Law': '#ff5722',
            'LawVersion': '#00bcd4',
            'ArticleVersion': '#1565c0',
            'Paragraph': '#2e7d32',
            'Item': '#6a1b9a',
            'Judgment': '#f57f17',
        }[type] || '#607d8b';
    }

    // ── Ingest button ─────────────────────────────────
    const btnIngest = document.getElementById('btn-ingest');
    btnIngest.addEventListener('click', async () => {
        btnIngest.disabled = true;
        btnIngest.innerText = 'جاري قراءة البيانات...';
        showToast('جاري معالجة الملفات وبناء قاعدة البيانات...');

        try {
            const res = await fetch('/api/ingest', { method: 'POST' });
            const result = await res.json();

            if (result.status === 'success') {
                showToast('اكتملت المعالجة بنجاح! جاري إعادة تحميل...');
                // Reset state
                cy.elements().remove();
                nodeChildren.clear();
                expandedNodes.clear();
                setTimeout(loadLaws, 600);
            } else {
                showToast(`فشلت المعالجة: ${result.message}`);
            }
        } catch (err) {
            console.error(err);
            showToast('حدث خطأ أثناء معالجة المستندات');
        } finally {
            btnIngest.disabled = false;
            btnIngest.innerText = 'قراءة المستندات وإعادة البناء';
        }
    });

    // ── Toast ─────────────────────────────────────────
    function showToast(msg) {
        const toast = document.getElementById('toast');
        toast.innerText = msg;
        toast.classList.remove('hidden');
        clearTimeout(toast._timer);
        toast._timer = setTimeout(() => toast.classList.add('hidden'), 3500);
    }

    // ── Start ─────────────────────────────────────────
    initCytoscape();
    loadLaws();
});
