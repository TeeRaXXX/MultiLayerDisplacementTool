# gn_multires.py — Реализация multiresolution вместо subdivision surface

from __future__ import annotations
import bpy
from .constants import GN_MOD_NAME

# Константа для multiresolution GN
MULTIRES_GN_MOD_NAME = "MLD_MultiresGN"

def _test_multiresolution_working(obj: bpy.types.Object, level: int) -> bool:
    """Тестовая функция для проверки работы multiresolution."""
    try:
        print(f"[MLD] Testing multiresolution with level {level}...")
        
        # Создаем временный multiresolution modifier
        test_md = obj.modifiers.new("MLD_Test_Multires", 'MULTIRES')
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
            
            print(f"[MLD] Test multiresolution: {original_verts} → {test_verts} verts, {original_polys} → {test_polys} polys")
            
            # Удаляем тестовый модификатор
            obj.modifiers.remove(test_md)
            
            if test_verts > original_verts or test_polys > original_polys:
                print(f"[MLD] ✓ Standard multiresolution works")
                return True
            else:
                print(f"[MLD] ✗ Standard multiresolution failed")
                return False
        else:
            obj.modifiers.remove(test_md)
            return False
            
    except Exception as e:
        print(f"[MLD] Test multiresolution failed: {e}")
        # Удаляем тестовый модификатор если есть
        test_md = obj.modifiers.get("MLD_Test_Multires")
        if test_md:
            try:
                obj.modifiers.remove(test_md)
            except Exception:
                pass
        return False

def _make_multires_group_interface_45(ng: bpy.types.NodeTree):
    """Создать интерфейс для multiresolution geometry nodes группы (Blender 4.x)."""
    try:
        iface = ng.interface
        # Создаем сокеты в правильном порядке
        iface.new_socket(name="Geometry", in_out='INPUT',  socket_type='NodeSocketGeometry')
        iface.new_socket(name="Level", in_out='INPUT', socket_type='NodeSocketInt')
        iface.new_socket(name="Geometry", in_out='OUTPUT', socket_type='NodeSocketGeometry')
        print(f"[MLD] ✓ Created multiresolution node group interface with sockets")
    except Exception as e:
        print(f"[MLD] ✗ Failed to create interface: {e}")

def _build_multires_graph_simple(ng: bpy.types.NodeTree):
    """Построить ПРОСТЕЙШИЙ рабочий граф multiresolution."""
    nodes, links = ng.nodes, ng.links
    nodes.clear()

    try:
        # Input/Output nodes
        n_in = nodes.new("NodeGroupInput")
        n_in.location = (-400, 0)
        n_out = nodes.new("NodeGroupOutput")
        n_out.location = (400, 0)

        # Multiresolution node
        n_multires = nodes.new("GeometryNodeMultires")
        n_multires.location = (0, 0)
        
        # Устанавливаем базовые параметры multiresolution
        if hasattr(n_multires, 'boundary_smooth'):
            n_multires.boundary_smooth = 'ALL'
        if hasattr(n_multires, 'uv_smooth'):
            n_multires.uv_smooth = 'PRESERVE_BOUNDARIES'
        
        # Устанавливаем default level для multiresolution node
        if hasattr(n_multires, 'inputs') and 'Level' in n_multires.inputs:
            n_multires.inputs['Level'].default_value = 2  # Default level

        # ДЕТАЛЬНАЯ ДИАГНОСТИКА multiresolution node
        print(f"[MLD] Multiresolution node type: {n_multires.type}")
        print(f"[MLD] Multiresolution node bl_idname: {n_multires.bl_idname}")
        print(f"[MLD] Multiresolution node inputs: {[s.name for s in n_multires.inputs]}")
        print(f"[MLD] Multiresolution node outputs: {[s.name for s in n_multires.outputs]}")
        
        # Проверяем доступные атрибуты multiresolution node
        for attr in ['boundary_smooth', 'uv_smooth']:
            if hasattr(n_multires, attr):
                value = getattr(n_multires, attr)
                print(f"[MLD] Multiresolution node {attr}: {value}")

        # КРИТИЧЕСКИ ВАЖНО: правильные connections
        print(f"[MLD] Input sockets: {[s.name for s in n_in.outputs]}")
        print(f"[MLD] Multires inputs: {[s.name for s in n_multires.inputs]}")
        print(f"[MLD] Multires outputs: {[s.name for s in n_multires.outputs]}")
        print(f"[MLD] Output sockets: {[s.name for s in n_out.inputs]}")

        # Подключения с проверкой
        if "Geometry" in [s.name for s in n_in.outputs] and "Mesh" in [s.name for s in n_multires.inputs]:
            links.new(n_in.outputs["Geometry"], n_multires.inputs["Mesh"])
            print(f"[MLD] ✓ Connected Geometry → Mesh")
        else:
            print(f"[MLD] ✗ Failed to connect Geometry → Mesh")

        if "Level" in [s.name for s in n_in.outputs] and "Level" in [s.name for s in n_multires.inputs]:
            links.new(n_in.outputs["Level"], n_multires.inputs["Level"])
            print(f"[MLD] ✓ Connected Level → Level")
        else:
            print(f"[MLD] ✗ Failed to connect Level → Level")

        if "Mesh" in [s.name for s in n_multires.outputs] and "Geometry" in [s.name for s in n_out.inputs]:
            links.new(n_multires.outputs["Mesh"], n_out.inputs["Geometry"])
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
                links.new(n_in.outputs["Geometry"], n_multires.inputs["Mesh"])
                links.new(n_in.outputs["Level"], n_multires.inputs["Level"])
                links.new(n_multires.outputs["Mesh"], n_out.inputs["Geometry"])
                print(f"[MLD] ✓ Recreated all connections")
            except Exception as e:
                print(f"[MLD] ✗ Failed to recreate connections: {e}")

        print(f"[MLD] ✓ Multiresolution graph built successfully")
        return True

    except Exception as e:
        print(f"[MLD] ✗ Failed to build multiresolution graph: {e}")
        import traceback
        traceback.print_exc()
        return False

def _create_multires_group(obj: bpy.types.Object) -> bpy.types.GeometryNodeTree:
    """Создать Geometry Nodes группу для multiresolution."""
    name = f"MLD_MultiresGN::{obj.name}"
    
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
        _make_multires_group_interface_45(ng)
        
        # Построить граф
        success = _build_multires_graph_simple(ng)
        if not success:
            print(f"[MLD] ✗ Failed to build graph, removing group")
            try:
                bpy.data.node_groups.remove(ng, do_unlink=True)
            except Exception:
                pass
            return None
            
        return ng
        
    except Exception as e:
        print(f"[MLD] ✗ Failed to create multiresolution group: {e}")
        import traceback
        traceback.print_exc()
        return None

def _ensure_multires_gn_group(obj: bpy.types.Object) -> bpy.types.GeometryNodeTree:
    """Обеспечить существование рабочей Geometry Nodes группы для multiresolution."""
    # Всегда пересоздаем для гарантии работоспособности
    return _create_multires_group(obj)

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
                # Найти multiresolution node и установить level напрямую
                for node in ng.nodes:
                    if node.type == 'MULTIRES':
                        if hasattr(node, 'inputs') and 'Level' in node.inputs:
                            node.inputs['Level'].default_value = value
                            if verbose:
                                print(f"[MLD] ✓ Set multiresolution node Level = {value}")
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

def ensure_multires_gn(obj: bpy.types.Object, s) -> bpy.types.Modifier:
    """Создать/обновить multiresolution модификатор (используем стандартный MULTIRES вместо Geometry Nodes)."""
    print(f"[MLD] === ensure_multires_gn DEBUG ===")
    print(f"[MLD] Object: {obj.name}")
    print(f"[MLD] Settings object: {s}")
    print(f"[MLD] subdiv_enable value: {getattr(s, 'subdiv_enable', False)}")
    print(f"[MLD] subdiv_enable type: {type(getattr(s, 'subdiv_enable', False))}")
    print(f"[MLD] ================================")
    
    if not getattr(s, "subdiv_enable", False):
        print(f"[MLD] subdiv_enable is False, removing multiresolution modifier")
        remove_multires_gn(obj)
        return None

    # ДЕТАЛЬНАЯ ДИАГНОСТИКА настроек из UI
    print(f"[MLD] === MULTIRESOLUTION SETTINGS DEBUG ===")
    print(f"[MLD] subdiv_enable: {getattr(s, 'subdiv_enable', False)}")
    print(f"[MLD] subdiv_view: {getattr(s, 'subdiv_view', 1)}")
    print(f"[MLD] subdiv_type: {getattr(s, 'subdiv_type', 'SIMPLE')}")
    print(f"[MLD] subdiv_preserve_creases: {getattr(s, 'subdiv_preserve_creases', True)}")
    print(f"[MLD] subdiv_smooth_uvs: {getattr(s, 'subdiv_smooth_uvs', True)}")
    print(f"[MLD] ======================================")

    # Безопасная проверка уровней multiresolution
    raw_value = getattr(s, "subdiv_view", 1)
    print(f"[MLD] Raw subdiv_view from settings: {raw_value}")
    print(f"[MLD] Raw subdiv_view type: {type(raw_value)}")
    
    # ДОПОЛНИТЕЛЬНАЯ ДИАГНОСТИКА: проверим все возможные способы получения значения
    print(f"[MLD] === LEVEL VALUE DEBUG ===")
    print(f"[MLD] getattr(s, 'subdiv_view', 1): {getattr(s, 'subdiv_view', 1)}")
    try:
        print(f"[MLD] s.subdiv_view: {s.subdiv_view}")
    except Exception as e:
        print(f"[MLD] s.subdiv_view failed: {e}")
    try:
        print(f"[MLD] s['subdiv_view']: {s['subdiv_view']}")
    except Exception as e:
        print(f"[MLD] s['subdiv_view'] failed: {e}")
    print(f"[MLD] =========================")
    
    # Попробуем разные способы получения значения
    try:
        viewport_levels = int(raw_value)
    except (ValueError, TypeError):
        print(f"[MLD] Failed to convert {raw_value} to int, trying direct access")
        try:
            viewport_levels = s.subdiv_view
        except:
            print(f"[MLD] Direct access failed, using default")
            viewport_levels = 1
    
    print(f"[MLD] Final viewport_levels: {viewport_levels}")
    print(f"[MLD] Final viewport_levels type: {type(viewport_levels)}")
    
    if viewport_levels > 4:
        print(f"[MLD] WARNING: Multiresolution level {viewport_levels} limited to 4")
        viewport_levels = 4
    if viewport_levels < 0:
        viewport_levels = 0
        
    print(f"[MLD] Final multiresolution levels to apply: viewport={viewport_levels}")
    print(f"[MLD] Creating standard multiresolution modifier with level: {viewport_levels}")

    # Убедимся что объект в Object mode
    try:
        if obj.mode != 'OBJECT':
            bpy.ops.object.mode_set(mode='OBJECT')
    except Exception:
        pass

    # Удалить существующие multiresolution модификаторы
    remove_multires_gn(obj)

    # Создаем стандартный multiresolution modifier
    try:
        multires_md = obj.modifiers.new("MLD_Multires", 'MULTIRES')
        print(f"[MLD] ✓ Created standard multiresolution modifier")
        
        # ВАЖНО: В Blender 4.5 multiresolution требует инициализации через оператор
        print(f"[MLD] Initializing multiresolution with level: {viewport_levels}")
        
        # Устанавливаем активный объект для оператора
        bpy.context.view_layer.objects.active = obj
        
        # Инициализируем multiresolution через оператор
        try:
            bpy.ops.object.multires_subdivide(modifier=multires_md.name)
            print(f"[MLD] ✓ Applied initial subdivision")
        except Exception as e:
            print(f"[MLD] Warning: Could not apply initial subdivision: {e}")
        
        # Теперь устанавливаем нужный уровень
        multires_md.levels = viewport_levels
        multires_md.render_levels = viewport_levels
        
        # Принудительное обновление
        bpy.context.view_layer.update()
        
        # Проверяем что уровни установились
        initial_levels = multires_md.levels
        initial_render_levels = multires_md.render_levels
        print(f"[MLD] Initial levels check: {initial_levels}, render: {initial_render_levels}")
        
        # Если уровни не установились, попробуем альтернативный метод
        if initial_levels != viewport_levels:
            print(f"[MLD] ⚠ Levels not set correctly, trying alternative method...")
            try:
                # Попробуем применить subdivision несколько раз
                for i in range(viewport_levels):
                    bpy.ops.object.multires_subdivide(modifier=multires_md.name)
                    print(f"[MLD] Applied subdivision level {i+1}")
                
                # Проверяем результат
                final_levels = multires_md.levels
                final_render_levels = multires_md.render_levels
                print(f"[MLD] After multiple subdivisions - levels: {final_levels}, render: {final_render_levels}")
                
            except Exception as alt_e:
                print(f"[MLD] Alternative method failed: {alt_e}")
        
        print(f"[MLD] ✓ Initialized multiresolution modifier with level {viewport_levels}")
        
    except Exception as e:
        print(f"[MLD] ✗ Failed to create multiresolution modifier: {e}")
        return None

    # Финальная проверка и установка уровней
    try:
        # Проверяем текущие уровни
        current_levels = multires_md.levels
        current_render_levels = multires_md.render_levels
        print(f"[MLD] Current levels: viewport={current_levels}, render={current_render_levels}")
        
        # Если уровни не соответствуют требуемым, устанавливаем их
        if current_levels != viewport_levels:
            print(f"[MLD] Setting viewport levels to {viewport_levels}")
            multires_md.levels = viewport_levels
        
        if current_render_levels != viewport_levels:
            print(f"[MLD] Setting render levels to {viewport_levels}")
            multires_md.render_levels = viewport_levels
        
        # Принудительное обновление
        bpy.context.view_layer.update()
        
        # Финальная проверка
        final_levels = multires_md.levels
        final_render_levels = multires_md.render_levels
        print(f"[MLD] Final levels: viewport={final_levels}, render={final_render_levels}")
        
        # Проверяем что модификатор активен
        print(f"[MLD] Modifier show_viewport: {multires_md.show_viewport}")
        print(f"[MLD] Modifier show_render: {multires_md.show_render}")
            
    except Exception as e:
        print(f"[MLD] ✗ Failed to set multiresolution levels: {e}")
        import traceback
        traceback.print_exc()
        return None

    # Проверяем что уровень установился правильно
    actual_levels = multires_md.levels
    actual_render_levels = multires_md.render_levels
    print(f"[MLD] Actual modifier levels: viewport={actual_levels}, render={actual_render_levels}")
    
    if actual_levels != viewport_levels:
        print(f"[MLD] ⚠ WARNING: Viewport level mismatch! Requested {viewport_levels}, got {actual_levels}")
        # Попробуем принудительно установить
        try:
            multires_md.levels = viewport_levels
            print(f"[MLD] Forced viewport level to {viewport_levels}")
        except Exception as e:
            print(f"[MLD] Failed to force viewport level: {e}")
    
    if actual_render_levels != viewport_levels:
        print(f"[MLD] ⚠ WARNING: Render level mismatch! Requested {viewport_levels}, got {actual_render_levels}")
        # Попробуем принудительно установить
        try:
            multires_md.render_levels = viewport_levels
            print(f"[MLD] Forced render level to {viewport_levels}")
        except Exception as e:
            print(f"[MLD] Failed to force render level: {e}")

    # ПРОВЕРКА что multiresolution действительно работает
    multires_working = False
    try:
        original_verts = len(obj.data.vertices)
        original_polys = len(obj.data.polygons)
        
        # Принудительное обновление перед проверкой
        bpy.context.view_layer.update()
        
        # Получаем evaluated mesh для проверки
        depsgraph = bpy.context.evaluated_depsgraph_get()
        obj_eval = obj.evaluated_get(depsgraph)
        if obj_eval and obj_eval.data:
            subdivided_verts = len(obj_eval.data.vertices)
            subdivided_polys = len(obj_eval.data.polygons)
            
            print(f"[MLD] Mesh complexity check: {original_verts} → {subdivided_verts} verts, {original_polys} → {subdivided_polys} polys")
            
            # Проверяем что multiresolution действительно увеличил сложность
            if subdivided_verts > original_verts or subdivided_polys > original_polys:
                print(f"[MLD] ✓ Multiresolution is working: mesh complexity increased")
                multires_working = True
            else:
                print(f"[MLD] ⚠ Multiresolution may not be working: no complexity increase")
                print(f"[MLD] Expected increase: {original_verts} → ~{original_verts * (4 ** viewport_levels)} vertices")
                
                # Попробуем принудительно обновить еще раз
                print(f"[MLD] Trying additional force update...")
                bpy.context.view_layer.update()
                bpy.context.view_layer.update()
                
                # Проверяем еще раз
                obj_eval = obj.evaluated_get(depsgraph)
                if obj_eval and obj_eval.data:
                    subdivided_verts2 = len(obj_eval.data.vertices)
                    if subdivided_verts2 > original_verts:
                        print(f"[MLD] ✓ After additional update: {original_verts} → {subdivided_verts2} vertices")
                        multires_working = True
                    else:
                        print(f"[MLD] ✗ Still no increase after additional update")
    except Exception as e:
        print(f"[MLD] Warning: multiresolution verification failed: {e}")

    # ФИНАЛЬНАЯ ПРОВЕРКА
    print(f"[MLD] === FINAL MULTIRESOLUTION VERIFICATION ===")
    print(f"[MLD] Modifier levels: {multires_md.levels}")
    print(f"[MLD] Modifier render_levels: {multires_md.render_levels}")
    print(f"[MLD] Modifier show_viewport: {multires_md.show_viewport}")
    print(f"[MLD] Modifier show_render: {multires_md.show_render}")
    if multires_md.levels != viewport_levels:
        print(f"[MLD] ⚠ WARNING: Final level mismatch! Expected {viewport_levels}, got {multires_md.levels}")
    else:
        print(f"[MLD] ✓ Level correctly set to {viewport_levels}")
    print(f"[MLD] ==========================================")

    if multires_working:
        print(f"[MLD] ✓ Standard multiresolution configured successfully with level {viewport_levels}")
        return multires_md
    else:
        print(f"[MLD] ⚠ Multiresolution may not be working, but returning modifier anyway")
        return multires_md

def remove_multires_gn(obj: bpy.types.Object):
    """Удалить multiresolution модификаторы."""
    # Удаляем Geometry Nodes multiresolution modifier (если есть)
    md = obj.modifiers.get(MULTIRES_GN_MOD_NAME)
    if md:
        try: 
            obj.modifiers.remove(md)
            print(f"[MLD] Removed multiresolution GN modifier")
        except Exception: 
            pass
    
    # Удаляем стандартный multiresolution modifier
    multires_md = obj.modifiers.get("MLD_Multires")
    if multires_md:
        try:
            obj.modifiers.remove(multires_md)
            print(f"[MLD] Removed standard multiresolution modifier")
        except Exception:
            pass
    

    
    # Также удалить связанную node group (если есть)
    name = f"MLD_MultiresGN::{obj.name}"
    ng = bpy.data.node_groups.get(name)
    if ng:
        try:
            bpy.data.node_groups.remove(ng, do_unlink=True)
            print(f"[MLD] Removed multiresolution node group: {name}")
        except Exception:
            pass

def ensure_modifier_order(obj: bpy.types.Object):
    """Обеспечить правильный порядок модификаторов: Multires -> DisplaceGN -> DecimateGN."""
    modifiers = obj.modifiers
    
    if not modifiers:
        return
    
    # Определить целевой порядок
    target_order = []
    if MULTIRES_GN_MOD_NAME in [m.name for m in modifiers]:
        target_order.append(MULTIRES_GN_MOD_NAME)
    if "MLD_Multires" in [m.name for m in modifiers]:  # Стандартный multiresolution
        target_order.append("MLD_Multires")
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
