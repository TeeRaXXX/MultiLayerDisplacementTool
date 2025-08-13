# gn_subdiv.py — РАБОЧЕЕ ИСПРАВЛЕНИЕ (правильная установка inputs)

from __future__ import annotations
import bpy
from .constants import GN_MOD_NAME

# Новая константа для subdivision GN
SUBDIV_GN_MOD_NAME = "MLD_SubdivGN"

def _test_subdivision_working(obj: bpy.types.Object, level: int) -> bool:
    """Тестовая функция для проверки работы subdivision."""
    try:
        print(f"[MLD] Testing subdivision with level {level}...")
        
        # Создаем временный стандартный subdivision modifier
        test_md = obj.modifiers.new("MLD_Test_Subdiv", 'SUBSURF')
        test_md.levels = level
        test_md.render_levels = level
        
        # Принудительное обновление
        bpy.context.view_layer.update()
        
        # Проверяем результат
        original_verts = len(obj.data.vertices)
        original_polys = len(obj.data.polygons)
        
        depsgraph = bpy.context.evaluated_depsgraph_get()
        obj_eval = obj.evaluated_get(depsgraph)
        if obj_eval and obj_eval.data:
            test_verts = len(obj_eval.data.vertices)
            test_polys = len(obj_eval.data.polygons)
            
            print(f"[MLD] Test subdivision: {original_verts} → {test_verts} verts, {original_polys} → {test_polys} polys")
            
            # Удаляем тестовый модификатор
            obj.modifiers.remove(test_md)
            
            if test_verts > original_verts or test_polys > original_polys:
                print(f"[MLD] ✓ Standard subdivision works")
                return True
            else:
                print(f"[MLD] ✗ Standard subdivision failed")
                return False
        else:
            obj.modifiers.remove(test_md)
            return False
            
    except Exception as e:
        print(f"[MLD] Test subdivision failed: {e}")
        # Удаляем тестовый модификатор если есть
        test_md = obj.modifiers.get("MLD_Test_Subdiv")
        if test_md:
            try:
                obj.modifiers.remove(test_md)
            except Exception:
                pass
        return False

def _make_subdiv_group_interface_45(ng: bpy.types.NodeTree):
    """Создать интерфейс для subdivision geometry nodes группы (Blender 4.x)."""
    try:
        iface = ng.interface
        # Создаем сокеты в правильном порядке
        iface.new_socket(name="Geometry", in_out='INPUT',  socket_type='NodeSocketGeometry')
        iface.new_socket(name="Level", in_out='INPUT', socket_type='NodeSocketInt')
        iface.new_socket(name="Geometry", in_out='OUTPUT', socket_type='NodeSocketGeometry')
        print(f"[MLD] ✓ Created node group interface with sockets")
    except Exception as e:
        print(f"[MLD] ✗ Failed to create interface: {e}")

def _build_subdiv_graph_simple(ng: bpy.types.NodeTree):
    """Построить ПРОСТЕЙШИЙ рабочий граф subdivision."""
    nodes, links = ng.nodes, ng.links
    nodes.clear()

    try:
        # Input/Output nodes
        n_in = nodes.new("NodeGroupInput")
        n_in.location = (-400, 0)
        n_out = nodes.new("NodeGroupOutput")
        n_out.location = (400, 0)

        # Subdivision Surface node
        n_subdiv = nodes.new("GeometryNodeSubdivisionSurface")
        n_subdiv.location = (0, 0)
        
        # Устанавливаем базовые параметры subdivision
        if hasattr(n_subdiv, 'boundary_smooth'):
            n_subdiv.boundary_smooth = 'ALL'
        if hasattr(n_subdiv, 'uv_smooth'):
            n_subdiv.uv_smooth = 'PRESERVE_BOUNDARIES'
        
        # Устанавливаем subdivision type если доступно
        if hasattr(n_subdiv, 'subdivision_type'):
            n_subdiv.subdivision_type = 'CATMULL_CLARK'
        
        # Устанавливаем default level для subdivision node
        if hasattr(n_subdiv, 'inputs') and 'Level' in n_subdiv.inputs:
            n_subdiv.inputs['Level'].default_value = 2  # Default level

        # ДЕТАЛЬНАЯ ДИАГНОСТИКА subdivision node
        print(f"[MLD] Subdivision node type: {n_subdiv.type}")
        print(f"[MLD] Subdivision node bl_idname: {n_subdiv.bl_idname}")
        print(f"[MLD] Subdivision node inputs: {[s.name for s in n_subdiv.inputs]}")
        print(f"[MLD] Subdivision node outputs: {[s.name for s in n_subdiv.outputs]}")
        
        # Проверяем доступные атрибуты subdivision node
        for attr in ['boundary_smooth', 'uv_smooth', 'subdivision_type']:
            if hasattr(n_subdiv, attr):
                value = getattr(n_subdiv, attr)
                print(f"[MLD] Subdivision node {attr}: {value}")

        # КРИТИЧЕСКИ ВАЖНО: правильные connections
        print(f"[MLD] Input sockets: {[s.name for s in n_in.outputs]}")
        print(f"[MLD] Subdiv inputs: {[s.name for s in n_subdiv.inputs]}")
        print(f"[MLD] Subdiv outputs: {[s.name for s in n_subdiv.outputs]}")
        print(f"[MLD] Output sockets: {[s.name for s in n_out.inputs]}")

        # Подключения с проверкой
        if "Geometry" in [s.name for s in n_in.outputs] and "Mesh" in [s.name for s in n_subdiv.inputs]:
            links.new(n_in.outputs["Geometry"], n_subdiv.inputs["Mesh"])
            print(f"[MLD] ✓ Connected Geometry → Mesh")
        else:
            print(f"[MLD] ✗ Failed to connect Geometry → Mesh")

        if "Level" in [s.name for s in n_in.outputs] and "Level" in [s.name for s in n_subdiv.inputs]:
            links.new(n_in.outputs["Level"], n_subdiv.inputs["Level"])
            print(f"[MLD] ✓ Connected Level → Level")
        else:
            print(f"[MLD] ✗ Failed to connect Level → Level")

        if "Mesh" in [s.name for s in n_subdiv.outputs] and "Geometry" in [s.name for s in n_out.inputs]:
            links.new(n_subdiv.outputs["Mesh"], n_out.inputs["Geometry"])
            print(f"[MLD] ✓ Connected Mesh → Geometry")
        else:
            print(f"[MLD] ✗ Failed to connect Mesh → Geometry")

        # ДОПОЛНИТЕЛЬНАЯ ПРОВЕРКА: убедимся что все connections установлены
        if len(links) < 3:
            print(f"[MLD] ⚠ Warning: Only {len(links)} connections made, expected 3")
            # Попробуем принудительно создать connections
            try:
                # Очистим существующие connections
                links.clear()
                
                # Создадим connections заново
                links.new(n_in.outputs["Geometry"], n_subdiv.inputs["Mesh"])
                links.new(n_in.outputs["Level"], n_subdiv.inputs["Level"])
                links.new(n_subdiv.outputs["Mesh"], n_out.inputs["Geometry"])
                print(f"[MLD] ✓ Recreated all connections")
            except Exception as e:
                print(f"[MLD] ✗ Failed to recreate connections: {e}")

        print(f"[MLD] ✓ Subdivision graph built successfully")
        return True

    except Exception as e:
        print(f"[MLD] ✗ Failed to build subdivision graph: {e}")
        import traceback
        traceback.print_exc()
        return False

def _create_subdiv_group(obj: bpy.types.Object) -> bpy.types.GeometryNodeTree:
    """Создать Geometry Nodes группу для subdivision."""
    name = f"MLD_SubdivGN::{obj.name}"
    
    # Удалить существующую группу если есть
    existing = bpy.data.node_groups.get(name)
    if existing:
        try:
            bpy.data.node_groups.remove(existing, do_unlink=True)
            print(f"[MLD] Removed existing node group: {name}")
        except Exception as e:
            print(f"[MLD] Warning: could not remove existing group: {e}")
    
    try:
        # Создать новую группу
        ng = bpy.data.node_groups.new(name=name, type='GeometryNodeTree')
        print(f"[MLD] ✓ Created node group: {name}")
        
        # Создать интерфейс
        _make_subdiv_group_interface_45(ng)
        
        # Построить граф
        success = _build_subdiv_graph_simple(ng)
        if not success:
            print(f"[MLD] ✗ Failed to build graph, removing group")
            try:
                bpy.data.node_groups.remove(ng, do_unlink=True)
            except Exception:
                pass
            return None
            
        return ng
        
    except Exception as e:
        print(f"[MLD] ✗ Failed to create subdivision group: {e}")
        import traceback
        traceback.print_exc()
        return None

def _ensure_subdiv_gn_group(obj: bpy.types.Object) -> bpy.types.GeometryNodeTree:
    """Обеспечить существование рабочей Geometry Nodes группы для subdivision."""
    # Всегда пересоздаваем для гарантии работоспособности
    return _create_subdiv_group(obj)

def _set_modifier_input_value(md, input_name: str, value, verbose=True):
    """УЛУЧШЕННАЯ функция установки значения input в modifier с детальной диагностикой."""
    try:
        if verbose:
            print(f"[MLD] Attempting to set {input_name} = {value}")
        
        # Метод 1: Новая система через md.inputs (Blender 4.x)
        if hasattr(md, "inputs") and md.inputs:
            if verbose:
                print(f"[MLD] Available inputs: {list(md.inputs.keys())}")
            
            if input_name in md.inputs:
                # Прямая установка
                md.inputs[input_name].default_value = value
                if verbose:
                    actual = md.inputs[input_name].default_value
                    print(f"[MLD] ✓ Set {input_name} = {value}, verified = {actual}")
                return True
            else:
                if verbose:
                    print(f"[MLD] ⚠ Input '{input_name}' not found in modifier inputs")
        
        # Метод 2: Legacy система через индексы
        if input_name == "Level":
            try:
                # Пробуем разные индексы для Level input
                for idx in [1, 2, "Input_2", "Input_1"]:
                    try:
                        md[f"Input_{idx}"] = value
                        if verbose:
                            print(f"[MLD] ✓ Set legacy input_{idx} = {value}")
                        return True
                    except Exception:
                        continue
                        
                # Прямое обращение к атрибуту
                md["Level"] = value
                if verbose:
                    print(f"[MLD] ✓ Set direct Level = {value}")
                return True
                
            except Exception as e:
                if verbose:
                    print(f"[MLD] ⚠ Legacy input setting failed: {e}")
        
        # Метод 3: Через node group inputs (если модификатор еще не полностью инициализирован)
        if hasattr(md, "node_group") and md.node_group:
            ng = md.node_group
            if hasattr(ng, "interface") and ng.interface:
                try:
                    # Найти input socket в interface
                    for socket in ng.interface.items_tree:
                        if hasattr(socket, 'name') and socket.name == input_name:
                            if hasattr(socket, 'default_value'):
                                socket.default_value = value
                                if verbose:
                                    print(f"[MLD] ✓ Set node group interface {input_name} = {value}")
                                return True
                except Exception as e:
                    if verbose:
                        print(f"[MLD] ⚠ Node group interface setting failed: {e}")
        
        # Метод 4: Через node group nodes напрямую
        if hasattr(md, "node_group") and md.node_group:
            ng = md.node_group
            try:
                # Найти subdivision node и установить level напрямую
                for node in ng.nodes:
                    if node.type == 'SUBDIVISION_SURFACE':
                        if hasattr(node, 'inputs') and 'Level' in node.inputs:
                            node.inputs['Level'].default_value = value
                            if verbose:
                                print(f"[MLD] ✓ Set subdivision node Level = {value}")
                            return True
            except Exception as e:
                if verbose:
                    print(f"[MLD] ⚠ Direct node setting failed: {e}")
        
        # Метод 5: Через dictionary access
        try:
            md[input_name] = value
            if verbose:
                print(f"[MLD] ✓ Set via dictionary access {input_name} = {value}")
            return True
        except Exception as e:
            if verbose:
                print(f"[MLD] ⚠ Dictionary access failed: {e}")
        
        if verbose:
            print(f"[MLD] ✗ All methods failed to set {input_name}")
        return False
        
    except Exception as e:
        if verbose:
            print(f"[MLD] ✗ Exception setting {input_name}: {e}")
        return False

def ensure_subdiv_gn(obj: bpy.types.Object, s) -> bpy.types.NodesModifier:
    """Создать/обновить Geometry Nodes модификатор для subdivision (РАБОЧАЯ ВЕРСИЯ)."""
    if not getattr(s, "subdiv_enable", False):
        remove_subdiv_gn(obj)
        return None

    # ДЕТАЛЬНАЯ ДИАГНОСТИКА настроек из UI
    print(f"[MLD] === SUBDIVISION SETTINGS DEBUG ===")
    print(f"[MLD] subdiv_enable: {getattr(s, 'subdiv_enable', False)}")
    print(f"[MLD] subdiv_view: {getattr(s, 'subdiv_view', 1)}")
    print(f"[MLD] subdiv_render: {getattr(s, 'subdiv_render', 1)}")
    print(f"[MLD] subdiv_type: {getattr(s, 'subdiv_type', 'SIMPLE')}")
    print(f"[MLD] subdiv_preserve_creases: {getattr(s, 'subdiv_preserve_creases', True)}")
    print(f"[MLD] subdiv_smooth_uvs: {getattr(s, 'subdiv_smooth_uvs', True)}")
    print(f"[MLD] =================================")

    # Безопасная проверка уровней subdivision
    viewport_levels = int(getattr(s, "subdiv_view", 1))
    print(f"[MLD] Raw subdiv_view from settings: {getattr(s, 'subdiv_view', 1)}")
    print(f"[MLD] Converted to int: {viewport_levels}")
    print(f"[MLD] Type of viewport_levels: {type(viewport_levels)}")
    
    if viewport_levels > 4:
        print(f"[MLD] WARNING: Subdivision level {viewport_levels} limited to 4")
        viewport_levels = 4
    if viewport_levels < 0:
        viewport_levels = 0

    print(f"[MLD] Final subdivision level to apply: {viewport_levels}")
    print(f"[MLD] Creating subdivision GN with level: {viewport_levels}")
    
    # ДОПОЛНИТЕЛЬНАЯ ПРОВЕРКА: убедимся что значение не изменилось
    if viewport_levels != int(getattr(s, "subdiv_view", 1)):
        print(f"[MLD] ⚠ WARNING: viewport_levels was modified! Original: {getattr(s, 'subdiv_view', 1)}, Final: {viewport_levels}")
    else:
        print(f"[MLD] ✓ viewport_levels unchanged: {viewport_levels}")

    # Проверяем что subdivision вообще работает на этом объекте
    if viewport_levels > 0:
        subdivision_test = _test_subdivision_working(obj, viewport_levels)
        if not subdivision_test:
            print(f"[MLD] ⚠ Subdivision test failed - subdivision may not work on this mesh")
            print(f"[MLD] Mesh info: {len(obj.data.vertices)} vertices, {len(obj.data.polygons)} polygons")
            # Продолжаем попытку с Geometry Nodes

    # Убедимся что объект в Object mode
    try:
        if obj.mode != 'OBJECT':
            bpy.ops.object.mode_set(mode='OBJECT')
    except Exception:
        pass

    # Удалить существующий модификатор
    md = obj.modifiers.get(SUBDIV_GN_MOD_NAME)
    if md:
        try:
            obj.modifiers.remove(md)
            print(f"[MLD] Removed existing subdivision GN modifier")
        except Exception as e:
            print(f"[MLD] Warning: could not remove existing modifier: {e}")

    # Создать node group
    ng = _ensure_subdiv_gn_group(obj)
    if not ng:
        print(f"[MLD] ✗ Failed to create node group")
        return None

    # Создать новый модификатор
    try:
        md = obj.modifiers.new(SUBDIV_GN_MOD_NAME, 'NODES')
        print(f"[MLD] ✓ Created subdivision GN modifier")
    except Exception as e:
        print(f"[MLD] ✗ Failed to create modifier: {e}")
        return None

    # Назначить node group
    try:
        md.node_group = ng
        print(f"[MLD] ✓ Assigned node group to modifier")
    except Exception as e:
        print(f"[MLD] ✗ Failed to assign node group: {e}")
        return None

    # МНОЖЕСТВЕННЫЕ ПРИНУДИТЕЛЬНЫЕ ОБНОВЛЕНИЯ для правильной инициализации
    for i in range(3):
        try:
            bpy.context.view_layer.update()
            print(f"[MLD] ✓ Update {i+1}/3 completed")
        except Exception as e:
            print(f"[MLD] Warning: update {i+1} failed: {e}")

    # УЛУЧШЕННАЯ установка параметров
    print(f"[MLD] Setting subdivision level using improved method...")
    
    success = _set_modifier_input_value(md, "Level", viewport_levels, verbose=True)
    
    if not success:
        print(f"[MLD] ✗ Failed to set Level input, trying manual verification...")
        
        # Попытка manual verification
        try:
            if hasattr(md, "inputs") and "Level" in md.inputs:
                current_val = md.inputs["Level"].default_value
                print(f"[MLD] Current Level value: {current_val}")
                
                if current_val != viewport_levels:
                    # Принудительная установка через прямое обращение к данным
                    md.inputs["Level"].default_value = viewport_levels
                    bpy.context.view_layer.update()
                    
                    final_val = md.inputs["Level"].default_value
                    print(f"[MLD] Final Level value: {final_val}")
                    
                    if final_val == viewport_levels:
                        success = True
        except Exception as e:
            print(f"[MLD] Manual verification failed: {e}")

    # Финальные обновления
    for i in range(2):
        try:
            bpy.context.view_layer.update()
        except Exception:
            pass

    # ПРОВЕРКА что subdivision действительно работает
    subdivision_working = False
    try:
        original_verts = len(obj.data.vertices)
        original_polys = len(obj.data.polygons)
        
        # Получаем evaluated mesh для проверки
        depsgraph = bpy.context.evaluated_depsgraph_get()
        obj_eval = obj.evaluated_get(depsgraph)
        if obj_eval and obj_eval.data:
            subdivided_verts = len(obj_eval.data.vertices)
            subdivided_polys = len(obj_eval.data.polygons)
            
            print(f"[MLD] Mesh complexity check: {original_verts} → {subdivided_verts} verts, {original_polys} → {subdivided_polys} polys")
            
            # Проверяем что subdivision действительно увеличил сложность
            if subdivided_verts > original_verts or subdivided_polys > original_polys:
                print(f"[MLD] ✓ Subdivision is working: mesh complexity increased")
                subdivision_working = True
            else:
                print(f"[MLD] ⚠ Subdivision may not be working: no complexity increase")
                # Попробуем принудительно установить level еще раз
                if hasattr(md, "node_group") and md.node_group:
                    for node in md.node_group.nodes:
                        if node.type == 'SUBDIVISION_SURFACE':
                            if hasattr(node, 'inputs') and 'Level' in node.inputs:
                                node.inputs['Level'].default_value = viewport_levels
                                print(f"[MLD] Forced subdivision node level to {viewport_levels}")
                                bpy.context.view_layer.update()
                                break
    except Exception as e:
        print(f"[MLD] Warning: subdivision verification failed: {e}")

    # ДОПОЛНИТЕЛЬНАЯ ПРОВЕРКА: убедимся что настройки применились
    print(f"[MLD] === FINAL SUBDIVISION VERIFICATION ===")
    if hasattr(md, "inputs") and "Level" in md.inputs:
        final_level = md.inputs["Level"].default_value
        print(f"[MLD] Final modifier Level input: {final_level}")
        if final_level != viewport_levels:
            print(f"[MLD] ⚠ WARNING: Level mismatch! Expected {viewport_levels}, got {final_level}")
        else:
            print(f"[MLD] ✓ Level correctly set to {viewport_levels}")
    
    if hasattr(md, "node_group") and md.node_group:
        for node in md.node_group.nodes:
            if node.type == 'SUBDIVISION_SURFACE':
                if hasattr(node, 'inputs') and 'Level' in node.inputs:
                    node_level = node.inputs['Level'].default_value
                    print(f"[MLD] Subdivision node Level: {node_level}")
                    if node_level != viewport_levels:
                        print(f"[MLD] ⚠ WARNING: Node level mismatch! Expected {viewport_levels}, got {node_level}")
                    else:
                        print(f"[MLD] ✓ Node level correctly set to {viewport_levels}")
                break
    
    # ДОПОЛНИТЕЛЬНАЯ ПРОВЕРКА: убедимся что значение из UI сохранилось
    ui_level = getattr(s, "subdiv_view", 1)
    print(f"[MLD] UI setting subdiv_view: {ui_level}")
    if ui_level != viewport_levels:
        print(f"[MLD] ⚠ WARNING: UI level mismatch! UI shows {ui_level}, applied {viewport_levels}")
    else:
        print(f"[MLD] ✓ UI level matches applied level: {ui_level}")
    
    print(f"[MLD] ======================================")

    # FALLBACK: если Geometry Nodes subdivision не работает, используем стандартный subdivision modifier
    if not subdivision_working and viewport_levels > 0:
        print(f"[MLD] ⚠ Geometry Nodes subdivision not working, trying fallback to standard subdivision modifier")
        try:
            # Удаляем Geometry Nodes модификатор
            obj.modifiers.remove(md)
            
            # Создаем стандартный subdivision modifier
            subdiv_md = obj.modifiers.new("MLD_Subdiv", 'SUBSURF')
            print(f"[MLD] Created fallback subdivision modifier with requested level: {viewport_levels}")
            
            # Устанавливаем уровень subdivision
            subdiv_md.levels = viewport_levels
            subdiv_md.render_levels = viewport_levels
            
            # Проверяем что уровень установился правильно
            actual_levels = subdiv_md.levels
            actual_render_levels = subdiv_md.render_levels
            print(f"[MLD] Fallback modifier - requested: {viewport_levels}, actual levels: {actual_levels}, render_levels: {actual_render_levels}")
            
            if actual_levels != viewport_levels:
                print(f"[MLD] ⚠ WARNING: Fallback modifier level mismatch! Requested {viewport_levels}, got {actual_levels}")
                # Попробуем принудительно установить
                subdiv_md.levels = viewport_levels
                subdiv_md.render_levels = viewport_levels
                print(f"[MLD] Forced fallback modifier levels to {viewport_levels}")
            
            # Устанавливаем subdivision type
            subdiv_type = getattr(s, "subdiv_type", "SIMPLE")
            if subdiv_type == "CATMULL_CLARK":
                subdiv_md.subdivision_type = 'CATMULL_CLARK'
            else:
                subdiv_md.subdivision_type = 'SIMPLE'
            
            # ПРОВЕРКА fallback модификатора
            print(f"[MLD] === FALLBACK SUBDIVISION VERIFICATION ===")
            print(f"[MLD] Fallback modifier levels: {subdiv_md.levels}")
            print(f"[MLD] Fallback modifier render_levels: {subdiv_md.render_levels}")
            print(f"[MLD] Fallback modifier subdivision_type: {subdiv_md.subdivision_type}")
            if subdiv_md.levels != viewport_levels:
                print(f"[MLD] ⚠ WARNING: Fallback level mismatch! Expected {viewport_levels}, got {subdiv_md.levels}")
            else:
                print(f"[MLD] ✓ Fallback level correctly set to {viewport_levels}")
            print(f"[MLD] ===========================================")
            
            print(f"[MLD] ✓ Created fallback subdivision modifier with level {viewport_levels}")
            return subdiv_md
            
        except Exception as e:
            print(f"[MLD] ✗ Fallback subdivision also failed: {e}")
            return None

    if success or subdivision_working:
        print(f"[MLD] ✓ Subdivision GN configured successfully with level {viewport_levels}")
        
        # ФИНАЛЬНАЯ ПРОВЕРКА: убедимся что модификатор действительно имеет правильный уровень
        if hasattr(md, "inputs") and "Level" in md.inputs:
            final_input_level = md.inputs["Level"].default_value
            print(f"[MLD] Final verification - modifier input Level: {final_input_level}")
            if final_input_level != viewport_levels:
                print(f"[MLD] ⚠ CRITICAL: Modifier input level mismatch! Expected {viewport_levels}, got {final_input_level}")
                # Попробуем принудительно исправить
                md.inputs["Level"].default_value = viewport_levels
                bpy.context.view_layer.update()
                corrected_level = md.inputs["Level"].default_value
                print(f"[MLD] After correction - modifier input Level: {corrected_level}")
            else:
                print(f"[MLD] ✓ Modifier input level correctly set to {viewport_levels}")
        
        return md
    else:
        print(f"[MLD] ✗ Failed to configure subdivision level")
        # НЕ удаляем модификатор - может работать с default значениями
        return md

def remove_subdiv_gn(obj: bpy.types.Object):
    """Удалить Geometry Nodes модификатор subdivision."""
    # Удаляем Geometry Nodes subdivision modifier
    md = obj.modifiers.get(SUBDIV_GN_MOD_NAME)
    if md:
        try: 
            obj.modifiers.remove(md)
            print(f"[MLD] Removed subdivision GN modifier")
        except Exception: 
            pass
    
    # Удаляем fallback subdivision modifier
    fallback_md = obj.modifiers.get("MLD_Subdiv")
    if fallback_md:
        try:
            obj.modifiers.remove(fallback_md)
            print(f"[MLD] Removed fallback subdivision modifier")
        except Exception:
            pass
    
    # Также удалить связанную node group
    name = f"MLD_SubdivGN::{obj.name}"
    ng = bpy.data.node_groups.get(name)
    if ng:
        try:
            bpy.data.node_groups.remove(ng, do_unlink=True)
            print(f"[MLD] Removed subdivision node group: {name}")
        except Exception:
            pass

def ensure_modifier_order(obj: bpy.types.Object):
    """Обеспечить правильный порядок модификаторов: SubdivGN -> DisplaceGN -> DecimateGN."""
    modifiers = obj.modifiers
    
    if not modifiers:
        return
    
    # Определить целевой порядок
    target_order = []
    if SUBDIV_GN_MOD_NAME in [m.name for m in modifiers]:
        target_order.append(SUBDIV_GN_MOD_NAME)
    if "MLD_Subdiv" in [m.name for m in modifiers]:  # Fallback subdivision
        target_order.append("MLD_Subdiv")
    if GN_MOD_NAME in [m.name for m in modifiers]:
        target_order.append(GN_MOD_NAME)
    
    # Добавить decimate модификаторы
    decimate_mods = [mod.name for mod in modifiers if mod.name.startswith("MLD_Decimate")]
    target_order.extend(decimate_mods)
    
    if len(target_order) <= 1:
        return
    
    # Получить текущие позиции
    current_positions = {}
    for i, mod in enumerate(modifiers):
        if mod.name in target_order:
            current_positions[mod.name] = i
    
    # Безопасное перемещение модификаторов
    try:
        bpy.context.view_layer.objects.active = obj
        
        for target_pos, mod_name in enumerate(target_order):
            if mod_name not in current_positions:
                continue
                
            current_pos = current_positions[mod_name]
            
            if current_pos > target_pos:
                moves_needed = min(current_pos - target_pos, 10)
                for _ in range(moves_needed):
                    try:
                        bpy.ops.object.modifier_move_up(modifier=mod_name)
                    except Exception as e:
                        print(f"[MLD] Failed to move {mod_name}: {e}")
                        break
                print(f"[MLD] Moved {mod_name} up by {moves_needed} positions")
            
            # Обновить позиции
            for i, mod in enumerate(modifiers):
                if mod.name in target_order:
                    current_positions[mod.name] = i
                    
    except Exception as e:
        print(f"[MLD] Error in modifier ordering: {e}")

def register():
    pass

def unregister():
    pass