/* eslint-env jquery */


var Location = L.Editable.extend({

    _deleting: false,
    _deleted: false,
    _new: false,
    _dirty: false,

    layer: null,
    feature: null,

    initialize: function (map, options) {
        this._undoBuffer = {};
        this.on('editable:drawing:start', this._drawStart, this);
        this.on('editable:drawing:end', this._drawEnd, this);
        L.Editable.prototype.initialize.call(this, map, options);
    },

    // edit functions

    _startEdit: function () {
        if (this.layer) {
            this._backupLayer();
            this.layer.enableEdit(this.map);
            this.layer._dirty = true;
        }
    },

    _stopEdit: function () {
        if (this.layer) {
            this.layer.disableEdit(this.map);
            this._clearBackup();
        }
    },

    _saveEdit: function () {
        this.layer.disableEdit();
        var geom = this.layer.toGeoJSON().geometry;
        this.layer.feature.geometry = geom;
        this._backupLayer();
        var gj = JSON.stringify(geom);
        $('textarea[name="geometry"]').html(gj);
        this.layer._dirty = false;
    },

    _undoEdit: function () {
        this._undo();
        this.layer._dirty = false;
    },

    _undo: function () {
        if (this.layer) {
            this.layer.disableEdit();
            latLngs = this._undoBuffer[this.layer._leaflet_id];
            if (this.layer instanceof L.Marker) {
                this.layer.setLatLng(latLngs.latlngs);
                this.map.geojsonLayer.removeLayer(this.layer);
                this.map.geojsonLayer.addLayer(this.layer);
            } else {
                this.layer.setLatLngs(latLngs.latlngs);
            }
            this._clearBackup();
        }
    },

    // delete functions

    _startDelete: function () {
        this.layer.disableEdit();
        this._backupLayer();
        this._deleting = true;
        this._deleted = false;
    },

    _setDeleted: function (e) {
        if (this.layer instanceof L.Polyline || this.layer instanceof L.Polygon || this.layer instanceof L.Rectangle) {
            this.layer.enableEdit();
            this.layer.editor.deleteShape(this.layer._latlngs);
            this.layer.disableEdit();
            this._deleted = true;
        }
        if (this.layer instanceof L.Marker) {
            this.layer.enableEdit();
            this._backupLayer();
            this.layer.remove();
            this._deleted = true;
        }
        this.featuresLayer.clearLayers();
    },

    _undoDelete: function () {
        this._undo();
        this._deleted = false;
        this._deleting = false;
    },

    _saveDelete: function () {
        if (this._deleted) {
            $('textarea[name="geometry"]').html('');
            this.featuresLayer.clearLayers();
            this._clearBackup();
        }
        this._deleting = false;
    },

    // draw functions

    _drawStart: function (e) {},

    _drawEnd: function (e) {
        if (!this._hasDrawnFeature()) return;
        if (!this._checkValid(e.layer)) return;
        if (this.layer) {
            this._update(e.layer)
        } else {
            this._createNew(e.layer);
        }
        this.featuresLayer.clearLayers();
        this.layer.disableEdit();
        this.layer.dragging.disable();
        this._deleted = false;
        this._deleting = false;
    },

    _update: function (lyr) {
        this.layer.disableEdit();
        var geometry = lyr.toGeoJSON().geometry;
        var layer = LatLngUtil.copyLayer(lyr);
        L.stamp(layer);
        this.layer.feature.geometry = geometry;
        layer.feature = this.layer.feature;
        this.layer = layer;
        this._backupLayer();
        this._replaceGeoJSONFeature(this.layer);
        this.layer._dirty = true;
    },

    _createNew: function (lyr) {
        this.layer._new = true;
        this.layer._dirty = true;
        var feature = lyr.toGeoJSON();
        var layer = LatLngUtil.copyLayer(lyr);
        feature.id = L.stamp(layer);
        layer.feature = feature;
        this.layer = layer;
        this._backupLayer();
        this.map.geojsonLayer.addLayer(this.layer);
    },

    _checkValid: function (layer) {
        if (layer instanceof L.Polygon || layer instanceof L.Rectangle || layer instanceof L.Polyline) {
            // check if a feature has been drawn
            if (!layer.getBounds().isValid()) return false;
            var bounds = layer.getBounds(),
                nw = bounds.getNorthWest(),
                se = bounds.getSouthEast();
            if (nw.lat === se.lat && nw.lng === se.lng) {
                this.featuresLayer.removeLayer(layer);
                return false;
            }
            return true;
        } else {
            return true;
        }
    },

    // utils

    _replaceGeoJSONFeature(layer) {
        this.map.geojsonLayer.eachLayer(function (l) {
            if (l.feature.id === layer.feature.id) {
                l.remove();
                this.map.geojsonLayer.addLayer(layer);
            }
        }, this);
    },

    _backupLayer: function () {
        this._undoBuffer = {};
        if (this.layer instanceof L.Polyline || this.layer instanceof L.Polygon || this.layer instanceof L.Rectangle) {
            this._undoBuffer[this.layer._leaflet_id] = {
                latlngs: LatLngUtil.cloneLatLngs(this.layer.getLatLngs()),
            };
        }
        if (this.layer instanceof L.Marker) {
            this._undoBuffer[this.layer._leaflet_id] = {
                latlngs: LatLngUtil.cloneLatLng(this.layer.getLatLng()),
            }
        }
    },

    _hasDrawnFeature: function () {
        return this.featuresLayer.getLayers().length > 0;
    },

    _clearBackup: function () {
        this._undoBuffer = {};
    },

    _reset: function () {
        this.layer = null;
        this.feature = null;
        this.featuresLayer.clearLayers();
        this._clearBackup();
    },

});


var LocationEditor = L.Evented.extend({

    _editing: false,

    initialize: function (map, options) {
        this.map = map;
        map.locationEditor = this;
        this.location = new Location(map);
        map.editTools = this.location;
        this.toolbars = new EditorToolbars();

        this.tooltip = L.DomUtil.create(
            'div', 'editor-tooltip', L.DomUtil.get('mapid'));

        this._addRouterEvents();
        this._addEditableEvents();
    },

    onLayerClick: function (e) {
        if (this.dirty() && !this.deleting()) return;
        var feature = e.target.feature;
        var layer = e.layer || e.target
        if (this.editing() && feature.id !== this.location.layer.feature.id) return;
        if (this.deleting()) {
            this.deleteLayer(layer, e);
            return;
        }
        if (!this.editing()) {
            window.location.href = "#/" + feature.properties.url;
        }
        this.setEditable(feature, layer);
    },

    // edit functions

    setEditable: function (feature, layer) {
        if (this.location.layer) {
            Styles.resetStyle(this.location.layer);
        }
        layer.feature = feature;
        this.location.layer = layer;
        this.location.feature = feature;
        Styles.setSelectedStyle(layer);
    },

    edit: function () {
        this._addTooltip();
        if (this.editing()) {
            return;
        }
        this.location._startEdit();
    },

    cancelEdit: function () {
        this._removeTooltip();
        this.location._undoEdit();
    },

    editing: function () {
        return this._editing;
    },

    dirty: function () {
        if (this.location.layer) {
            return this.location.layer._dirty;
        }
    },

    _editStart: function (e) {
        this._editing = true;
        Styles.setEditStyle(e.layer);
    },

    _editStop: function (e) {
        this._editing = false;
        Styles.setSelectedStyle(e.layer);
    },

    // delete functions

    delete: function () {
        this._removeTooltip();
        this.location._saveDelete();
        if (this.location._deleted) {
            this._disableEditToolbar();
        } else {
            Styles.setSelectedStyle(this.location.layer);
        }
    },

    cancelDelete: function () {
        this._removeTooltip();
        this.location._undoDelete();
        Styles.setSelectedStyle(this.location.layer);
    },

    startDelete: function () {
        this._addTooltip();
        if (this.location.layer) {
            this.location._startDelete();
            Styles.setDeleteStyle(this.location.layer);
        }
    },

    deleting: function () {
        return this.location._deleting;
    },

    deleted: function () {
        return this.location._deleted;
    },

    deleteLayer: function (layer, e) {
        this.tooltip.innerHTML = 'Click cancel to undo or save to save deletion.'
        var currentLayer = this.location.layer;
        if (currentLayer.feature.id !== layer.feature.id) {
            return;
        }
        this.location._setDeleted(e);
    },

    // new location functions

    _addNew: function () {
        if (this._resetView()) {
            this.location._reset();
            this._addEditControls();
            this._disableEditToolbar();
        }
    },

    isNew: function () {
        if (this.location.layer) {
            return this.location.layer._new;
        }
    },

    // draw functions

    startRectangle: function () {
        this.location.startRectangle();
    },

    startPolygon: function () {
        this.location.startPolygon();
    },

    addMulti: function () {
        this.location.layer.editor.newShape();
    },

    startPolyline: function () {
        this.location.startPolyline();
    },

    startMarker: function () {
        this.location.startMarker();
    },

    hasEditableLayer: function () {
        return ((this.location.layer !== null ? true : false) ||
                this.hasDrawnFeature()) &&
            (!this.deleting() && !this.deleted());
    },

    hasDrawnFeature: function () {
        return this.location.featuresLayer.getLayers().length > 0;
    },

    cancelDrawing: function () {
        this.location.stopDrawing();
    },

    _drawStart: function (e) {
        this._addTooltip();
    },

    _drawEnd: function (e) {
        this._cancelDraw();
        this._removeTooltip();
        if (!this.location.layer._events.hasOwnProperty('click')) {
            this.location.layer.on('click', this.onLayerClick, this);
        }
        this._enableEditToolbar(active = true);
        Styles.setEditStyle(this.location.layer);
    },

    _vertexNew: function (e) {
        if (e.layer.editor instanceof L.Editable.PolylineEditor) {
            var latlngs = e.layer._latlngs;
            if (latlngs.length >= 1) {
                this.tooltip.innerHTML = 'Click on last point to finish line.';
            } else {
                this.tooltip.innerHTML = 'Click to continue line.';
            }
        }
        if (e.layer.editor instanceof L.Editable.PolygonEditor) {
            var latlngs = e.layer._latlngs[0];
            if (latlngs.length < 2) {
                this.tooltip.innerHTML = 'Click to continue adding vertices.';
            }
            if (latlngs.length >= 2 && e.layer.editor instanceof L.Editable.PolygonEditor) {
                this.tooltip.innerHTML = 'Click to continue adding vertices.<br/>' +
                    'Click last point to finish polygon.</span>';
            }
        }
    },

    _vertexDrag: function (e) {
        this.tooltip.innerHTML = 'Release mouse to finish drawing.';
        this._addTooltip();
    },

    _vertexDragend: function (e) {
        this._removeTooltip();
    },

    // saving

    save: function () {
        this._removeTooltip();
        this.location._saveEdit();
        this._editing = false;
    },

    // editor toolbars

    _findLayer: function (fid) {
        var layer = null;
        this.map.geojsonLayer.eachLayer(function (l) {
            if (l.feature.id === fid) {
                layer = l;
            }
        });
        return layer;
    },

    _setUpEditor: function (e) {
        if (!this.location.layer) {
            var hash_path = window.location.hash.slice(1) || '/';
            var fid = hash_path.split('/')[3];
            if (this.map.geojsonLayer.getLayers().length > 0) {
                var layer = this._findLayer(fid);
                this.location.layer = layer;
                Styles.setSelectedStyle(this.location.layer);
                this.edit();
                this._addEditControls();
            } else {
                this.map.on('endtileload', function () {
                    var layer = this._findLayer(fid);
                    this.location.layer = layer;
                    Styles.setSelectedStyle(this.location.layer);
                    this.edit();
                    this._addEditControls();
                }, this);
            }
        } else {
            this._addEditControls();
        }
    },

    _addEditControls: function () {
        const map = this.map;
        this.toolbars.forEach(function (toolbar) {
            toolbar.addTo(map);
        });
        this._enableEditToolbar(active = true);
    },

    _removeEditControls: function () {
        const map = this.map;
        this.toolbars.forEach(function (toolbar) {
            if (toolbar) {
                map.removeControl(toolbar);
            }
        });
        this.location._stopEdit();
        this._removeTooltip();
    },

    _enableEditToolbar: function (active = false) {
        var editLink = $('a.edit-action').get(0);
        var deleteLink = $('a.delete-action').get(0);
        editLink.href = window.location.href;
        deleteLink.href = window.location.href;
        if (active) {
            editLink.click();
            Styles.setEditStyle(this.location.layer);
        }
        $('span#edit, span#delete').removeClass('smap-edit-disable');
    },

    _disableEditToolbar: function () {
        var edit = $('ul.leaflet-smap-edit a').prop('disabled', 'disabled');
        $('span#edit, span#delete').addClass('smap-edit-disable');
    },

    _cancelEdit: function (reset = true) {
        var cancelEdit = $('a.cancel-edit'),
            cancelDelete = $('a.cancel-delete');
        if (cancelEdit.is(':visible')) {
            cancelEdit.get(0).click();
        };
        if (cancelDelete.is(':visible')) {
            cancelDelete.get(0).click();
        };
        if (this.location.layer && reset) {
            Styles.resetStyle(this.location.layer);
        }
    },

    _cancelDraw: function () {
        var cancelDraw = $('a.cancel-draw');
        cancelDraw.each(function (idx, ele) {
            if ($(ele).is(':visible')) {
                // ele.click();
                var ul = $(ele).closest('ul');
                $(ul).css('display', 'none');
            }
        });
    },

    _resetView: function () {
        this._editing = false;
        this._removeEditControls();
        Styles.resetStyle(this.location.layer);
        this.location._reset();
    },

    // tooltips

    _addTooltip: function () {
        L.DomEvent.on(this.map, 'mousemove', this._moveTooltip, this);
    },

    _removeTooltip: function () {
        this.tooltip.innerHTML = '';
        this.tooltip.style.display = 'none';
        L.DomEvent.off(this.map, 'mousemove', this._moveTooltip, this);
    },

    _moveTooltip: function (e) {
        if (this.tooltip.style.display === 'none') {
            this.tooltip.style.display = 'block';
        }
        this.tooltip.style.left = e.containerPoint.x + 'px';
        this.tooltip.style.top = e.containerPoint.y + 'px';
    },

    // events

    _addRouterEvents: function () {
        // router events
        this.on('route:location:edit', this._setUpEditor, this);
        this.on('route:location:new', this._addNew, this);
        this.on('route:location:detail', this._removeEditControls, this);
        this.on('route:overview', this._resetView, this);
    },

    _addEditableEvents: function () {
        // edit events
        this.location.on('editable:enable', this._editStart, this);
        this.location.on('editable:disable', this._editStop, this);
        this.location.on('editable:drawing:start', this._drawStart, this);
        this.location.on('editable:drawing:end', this._drawEnd, this);
        this.location.on('editable:vertex:drag', this._vertexDrag, this);
        this.location.on('editable:vertex:dragend', this._vertexDragend, this);
        this.location.on('editable:drawing:click', this._vertexNew, this);
    }

});
