import { useState, useCallback } from "react";
import { Ico, P } from "@/components/icons";
import { withAlpha } from "@/lib/color";

export type TreeNodeAction = {
  icon: React.ReactNode;
  label: string;
  onClick: (node: TreeNode) => void;
};

export type TreeNode = {
  id: string;
  icon?: React.ReactNode;
  label?: string;
  /** 重命名输入框预填值（只编辑名称部分）；缺省用 label 整串 */
  editValue?: string;
  badge?: string;
  badgeColor?: string;
  actions?: TreeNodeAction[];
  children?: TreeNode[];
  data?: unknown;
  locked?: boolean;
};

interface TreeCallbacks {
  selectedId?: string;
  onSelect: (node: TreeNode) => void;
  expandedIds: Set<string>;
  onToggle: (id: string) => void;
}

interface TreeProps extends TreeCallbacks {
  nodes: TreeNode[];
  /** Enable double-click to edit node titles */
  editable?: boolean;
  /** Enable lock icon on nodes with `node.locked = true` */
  locked?: boolean;
  /** Called when an edited title is confirmed */
  onTitleChange?: (nodeId: string, newTitle: string) => void;
  /** Called when a node delete is confirmed */
  onDelete?: (nodeId: string) => void;
  /** 行内新建插槽（FE-11）：卷节点 hover 渲染「+」 */
  onAddChild?: (node: TreeNode) => void;
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

/** Recursively find a node's edit value (rename prefill) by id. */
function findNodeEditValue(nodes: TreeNode[], id: string): string {
  for (const n of nodes) {
    if (n.id === id) return n.editValue ?? n.label ?? "";
    if (n.children) {
      const found = findNodeEditValue(n.children, id);
      if (found !== "") return found;
    }
  }
  return "";
}

// ---------------------------------------------------------------------------
// TreeNodeItem
// ---------------------------------------------------------------------------

interface TreeNodeItemProps extends TreeCallbacks {
  node: TreeNode;
  depth?: number;
  editable?: boolean;
  treeLocked?: boolean;
  onDelete?: (nodeId: string) => void;
  onAddChild?: (node: TreeNode) => void;
  editingId: string | null;
  editingValue: string;
  onStartEdit: (id: string, label: string) => void;
  onUpdateEdit: (value: string) => void;
  onCommitEdit: (id: string) => void;
  onCancelEdit: () => void;
  confirmingDeleteId: string | null;
  onStartDelete: (id: string) => void;
  onCommitDelete: (id: string) => void;
  onCancelDelete: () => void;
}

function TreeNodeItem({
  node,
  selectedId,
  onSelect,
  expandedIds,
  onToggle,
  depth = 0,
  editable,
  treeLocked,
  onDelete,
  onAddChild,
  editingId,
  editingValue,
  onStartEdit,
  onUpdateEdit,
  onCommitEdit,
  onCancelEdit,
  confirmingDeleteId,
  onStartDelete,
  onCommitDelete,
  onCancelDelete,
}: TreeNodeItemProps) {
  const isExpanded = expandedIds.has(node.id);
  const isSelected = selectedId === node.id;
  const hasChildren = node.children && node.children.length > 0;
  const isEditing = editingId === node.id;
  const isConfirmingDelete = confirmingDeleteId === node.id;
  const isLocked = treeLocked && node.locked;

  const handleEditKeyDown = useCallback(
    (e: React.KeyboardEvent<HTMLInputElement>) => {
      e.stopPropagation();
      if (e.key === "Enter") {
        e.preventDefault();
        onCommitEdit(node.id);
      } else if (e.key === "Escape") {
        onCancelEdit();
      }
    },
    [node.id, onCommitEdit, onCancelEdit],
  );

  const handleDoubleClick = useCallback(() => {
    if (editable && !isEditing) {
      onStartEdit(node.id, node.editValue ?? node.label ?? "");
    }
  }, [editable, isEditing, node.id, node.editValue, node.label, onStartEdit]);

  const showRightSide =
    (!isEditing && onDelete && !hasChildren) ||
    (node.actions && node.actions.length > 0) ||
    (!isEditing && onAddChild && hasChildren);

  return (
    <div>
      <div
        className={`stree-row row${isSelected ? " on" : ""}${isLocked ? " locked" : ""}`}
        style={{ paddingLeft: `${12 + depth * 16}px` }}
        onClick={() => onSelect(node)}
      >
        {/* Expand/collapse arrow */}
        {hasChildren ? (
          <button
            className="chev"
            onClick={(e) => {
              e.stopPropagation();
              onToggle(node.id);
            }}
          >
            <Ico d={isExpanded ? P.chevronDown : P.chevronRight} size={10} />
          </button>
        ) : (
          <span className="w-3 flex-shrink-0" />
        )}

        {/* Node icon */}
        {node.icon && (
          <span className="nicon">
            {node.icon}
          </span>
        )}

        {/* Lock icon */}
        {isLocked && (
          <Ico d={P.lock} size={12} className="flex-shrink-0" style={{ color: "var(--muted)" }} />
        )}

        {/* Label or Edit input */}
        {isEditing ? (
          <input
            className="edit"
            value={editingValue}
            onChange={(e) => onUpdateEdit(e.target.value)}
            onKeyDown={handleEditKeyDown}
            onBlur={() => onCommitEdit(node.id)}
            autoFocus
            onClick={(e) => e.stopPropagation()}
          />
        ) : (
          <span
            className="lbl"
            onDoubleClick={handleDoubleClick}
          >
            {node.label ?? "(未命名)"}
          </span>
        )}

        {/* Badge */}
        {node.badge && (
          <span
            className="badge"
            style={{
              backgroundColor: node.badgeColor
                ? withAlpha(node.badgeColor, 0.14)
                : "var(--fg-soft)",
              color: node.badgeColor ?? "var(--muted)",
            }}
          >
            {node.badge}
          </span>
        )}

        {/* Right side group (delete + existing actions) */}
        {showRightSide && (
          <div className="acts">
            {/* 行内新建插槽（FE-11）：卷节点 hover「+」 */}
            {onAddChild && hasChildren && (
              <button
                onClick={(e) => {
                  e.stopPropagation();
                  onAddChild(node);
                }}
                title="在卷下新建章节"
              >
                <Ico d={P.plus} size={12} />
              </button>
            )}

            {/* Delete button with inline confirmation */}
            {!isEditing && onDelete && !hasChildren &&
              (isConfirmingDelete ? (
                <span className="del-confirm stay">
                  <button
                    className="yes"
                    onClick={(e) => {
                      e.stopPropagation();
                      onCommitDelete(node.id);
                    }}
                  >
                    确认删除?
                  </button>
                  <button
                    className="no"
                    onClick={(e) => {
                      e.stopPropagation();
                      onCancelDelete();
                    }}
                  >
                    取消
                  </button>
                </span>
              ) : (
                <button
                  className="danger"
                  onClick={(e) => {
                    e.stopPropagation();
                    onStartDelete(node.id);
                  }}
                  title="删除"
                >
                  <Ico d={P.trash} size={12} />
                </button>
              ))}

            {/* Existing action buttons (visible on hover) */}
            {node.actions && node.actions.length > 0 &&
              node.actions.map((action, i) => (
                <button
                  key={i}
                  title={action.label}
                  onClick={(e) => {
                    e.stopPropagation();
                    action.onClick(node);
                  }}
                >
                  {action.icon}
                </button>
              ))}
          </div>
        )}
      </div>

      {/* Children (recursive) */}
      {hasChildren && isExpanded && (
        <div className="kids">
          {node.children!.map((child) => (
            <TreeNodeItem
              key={child.id}
              node={child}
              selectedId={selectedId}
              onSelect={onSelect}
              expandedIds={expandedIds}
              onToggle={onToggle}
              depth={depth + 1}
              editable={editable}
              treeLocked={treeLocked}
              onDelete={onDelete}
              onAddChild={onAddChild}
              editingId={editingId}
              editingValue={editingValue}
              onStartEdit={onStartEdit}
              onUpdateEdit={onUpdateEdit}
              onCommitEdit={onCommitEdit}
              onCancelEdit={onCancelEdit}
              confirmingDeleteId={confirmingDeleteId}
              onStartDelete={onStartDelete}
              onCommitDelete={onCommitDelete}
              onCancelDelete={onCancelDelete}
            />
          ))}
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export default function StructureTree({
  nodes,
  selectedId,
  onSelect,
  expandedIds,
  onToggle,
  editable,
  locked: treeLocked,
  onTitleChange,
  onDelete,
  onAddChild,
}: TreeProps) {
  const [editingId, setEditingId] = useState<string | null>(null);
  const [editingValue, setEditingValue] = useState("");
  const [confirmingDeleteId, setConfirmingDeleteId] = useState<string | null>(
    null,
  );

  const handleStartEdit = useCallback((id: string, label: string) => {
    setEditingId(id);
    setEditingValue(label);
  }, []);

  const handleUpdateEdit = useCallback((value: string) => {
    setEditingValue(value);
  }, []);

  const handleCommitEdit = useCallback(
    (id: string) => {
      const trimmed = editingValue.trim();
      const original = findNodeEditValue(nodes, id);
      if (trimmed && trimmed !== original) {
        onTitleChange?.(id, trimmed);
      }
      setEditingId(null);
      setEditingValue("");
    },
    [editingValue, nodes, onTitleChange],
  );

  const handleCancelEdit = useCallback(() => {
    setEditingId(null);
    setEditingValue("");
  }, []);

  const handleStartDelete = useCallback((id: string) => {
    setConfirmingDeleteId(id);
  }, []);

  const handleCommitDelete = useCallback(
    (id: string) => {
      onDelete?.(id);
      setConfirmingDeleteId(null);
    },
    [onDelete],
  );

  const handleCancelDelete = useCallback(() => {
    setConfirmingDeleteId(null);
  }, []);

  if (!nodes || nodes.length === 0) {
    return (
      <div className="stree tree-empty">
        暂无内容
      </div>
    );
  }

  return (
    <div className="stree">
      {nodes.map((node) => (
        <TreeNodeItem
          key={node.id}
          node={node}
          selectedId={selectedId}
          onSelect={onSelect}
          expandedIds={expandedIds}
          onToggle={onToggle}
          depth={0}
          editable={editable}
          treeLocked={treeLocked}
          onDelete={onDelete}
          onAddChild={onAddChild}
          editingId={editingId}
          editingValue={editingValue}
          onStartEdit={handleStartEdit}
          onUpdateEdit={handleUpdateEdit}
          onCommitEdit={handleCommitEdit}
          onCancelEdit={handleCancelEdit}
          confirmingDeleteId={confirmingDeleteId}
          onStartDelete={handleStartDelete}
          onCommitDelete={handleCommitDelete}
          onCancelDelete={handleCancelDelete}
        />
      ))}
    </div>
  );
}
