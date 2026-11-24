import { Copy, Pencil, Undo2 } from "lucide-react";
import { useState, type ReactNode } from "react";

import { Button } from "../../components/ui/Button";
import { Badge } from "../../components/ui/Feedback";
import { SelectInput, TextArea, TextInput } from "../../components/ui/Field";
import type { MemoryIndex } from "../../hooks/useMemoryIndex";
import type { ProposedDecision, ProposedTask } from "../../lib/api/types";
import { limits } from "../../lib/limits";
import { MemoryLink } from "../memory/MemoryLink";
import type { DecisionFields, ItemErrors, TaskFields } from "./approvalState";

const NO_ERRORS: ItemErrors = { fields: {} };

/** The frame of one proposed item: include checkbox, title row, body, editor and errors. */
function ItemFrame({
  anchor,
  title,
  selected,
  onToggle,
  edited,
  editing,
  onEdit,
  onUndo,
  errors,
  badges,
  children,
  editor,
}: {
  anchor: string;
  title: string;
  selected: boolean;
  onToggle: () => void;
  edited: boolean;
  editing: boolean;
  onEdit: () => void;
  onUndo: () => void;
  errors: ItemErrors;
  badges?: ReactNode;
  children: ReactNode;
  editor: ReactNode;
}) {
  const invalid = Boolean(errors.message) || Object.keys(errors.fields).length > 0;
  return (
    <li
      id={anchor}
      className={`space-y-2 rounded-lg border p-3 text-base ${invalid ? "border-danger" : "border-line"} ${selected ? "bg-paper" : "bg-sunken text-text-2"}`}
    >
      <div className="flex flex-wrap items-start gap-2">
        <input
          id={`${anchor}-include`}
          type="checkbox"
          checked={selected}
          onChange={onToggle}
          aria-label={`Include ${title}`}
          className="mt-1 size-4 accent-accent"
        />
        <label htmlFor={`${anchor}-include`} className="min-w-0 flex-1 break-words" dir="auto">
          {title}
        </label>
        {badges}
        {edited ? <Badge kind="info">edited</Badge> : null}
        <Button
          size="sm"
          aria-expanded={editing}
          aria-label={`${editing ? "Done editing" : "Edit"} ${title}`}
          aria-controls={`${anchor}-editor`}
          icon={<Pencil aria-hidden className="size-3" />}
          onClick={onEdit}
        >
          {editing ? "Done" : "Edit"}
        </Button>
        {edited ? (
          <Button
            size="sm"
            variant="ghost"
            aria-label={`Undo edits to ${title}`}
            icon={<Undo2 aria-hidden className="size-4" />}
            onClick={onUndo}
          />
        ) : null}
      </div>
      {errors.message ? (
        <p role="alert" className="text-danger">
          {errors.message}
        </p>
      ) : null}
      {children}
      {editing || invalid ? (
        <div id={`${anchor}-editor`} className="space-y-2 border-t border-line pt-2">
          {editor}
        </div>
      ) : null}
    </li>
  );
}

export function TaskItem({
  index,
  task,
  value,
  selected,
  errors = NO_ERRORS,
  titleOf,
  projectId,
  memory,
  onToggle,
  onChange,
  onUndo,
}: {
  index: number;
  task: ProposedTask;
  value: TaskFields;
  selected: boolean;
  errors?: ItemErrors | undefined;
  titleOf: (taskIndex: number) => string;
  projectId: string;
  memory: MemoryIndex;
  onToggle: () => void;
  onChange: (field: keyof TaskFields, value: string) => void;
  onUndo: () => void;
}) {
  const [editing, setEditing] = useState(false);
  const edited =
    value.title !== task.title ||
    value.description !== task.description ||
    value.priority !== task.priority;
  return (
    <ItemFrame
      anchor={`plan-task-${index}`}
      title={value.title}
      selected={selected}
      onToggle={onToggle}
      edited={edited}
      editing={editing}
      onEdit={() => {
        setEditing((v) => !v);
      }}
      onUndo={onUndo}
      errors={errors}
      badges={
        <>
          <Badge>{value.priority} priority</Badge>
          {task.possible_duplicate_of ? (
            <Badge kind="warning">
              <Copy aria-hidden className="size-3" /> possible duplicate
            </Badge>
          ) : null}
        </>
      }
      editor={
        <>
          <TextInput
            label="Title"
            value={value.title}
            maxLength={limits.memoryTitle}
            dir="auto"
            onChange={(e) => {
              onChange("title", e.target.value);
            }}
            error={errors.fields.title}
          />
          <TextArea
            label="Description"
            value={value.description}
            maxLength={limits.memoryText}
            onChange={(e) => {
              onChange("description", e.target.value);
            }}
            error={errors.fields.description}
          />
          <SelectInput
            label="Priority"
            value={value.priority}
            onChange={(e) => {
              onChange("priority", e.target.value);
            }}
            error={errors.fields.priority}
          >
            {["high", "medium", "low"].map((p) => (
              <option key={p} value={p}>
                {p}
              </option>
            ))}
          </SelectInput>
        </>
      }
    >
      {value.description ? (
        <p className="whitespace-pre-wrap break-words text-muted" dir="auto">
          {value.description}
        </p>
      ) : null}
      {task.acceptance_criteria.length > 0 ? (
        <div>
          <span className="eyebrow">Acceptance criteria</span>
          <ul className="list-disc pl-5">
            {task.acceptance_criteria.map((c, i) => (
              <li key={i} className="break-words" dir="auto">
                {c}
              </li>
            ))}
          </ul>
        </div>
      ) : null}
      {task.depends_on.length > 0 ? (
        <p>
          <span className="eyebrow">Depends on: </span>
          {task.depends_on.map((d, i) => (
            <span key={d}>
              {i > 0 ? ", " : null}
              <a href={`#plan-task-${d}`} dir="auto">
                {titleOf(d)}
              </a>
            </span>
          ))}
        </p>
      ) : null}
      {task.possible_duplicate_of ? (
        <p>
          <span className="eyebrow">Matches an existing task: </span>
          <MemoryLink projectId={projectId} id={task.possible_duplicate_of} index={memory} />
        </p>
      ) : null}
    </ItemFrame>
  );
}

export function DecisionItem({
  index,
  decision,
  value,
  selected,
  errors = NO_ERRORS,
  onToggle,
  onChange,
  onUndo,
}: {
  index: number;
  decision: ProposedDecision;
  value: DecisionFields;
  selected: boolean;
  errors?: ItemErrors | undefined;
  onToggle: () => void;
  onChange: (field: keyof DecisionFields, value: string) => void;
  onUndo: () => void;
}) {
  const [editing, setEditing] = useState(false);
  const fields: [keyof DecisionFields, string][] = [
    ["what", "What"],
    ["why", "Why"],
    ["alternatives", "Alternatives"],
  ];
  const edited = (["title", ...fields.map(([f]) => f)] as (keyof DecisionFields)[]).some(
    (f) => value[f] !== decision[f],
  );
  return (
    <ItemFrame
      anchor={`plan-decision-${index}`}
      title={value.title}
      selected={selected}
      onToggle={onToggle}
      edited={edited}
      editing={editing}
      onEdit={() => {
        setEditing((v) => !v);
      }}
      onUndo={onUndo}
      errors={errors}
      editor={
        <>
          <TextInput
            label="Title"
            value={value.title}
            maxLength={limits.memoryTitle}
            dir="auto"
            onChange={(e) => {
              onChange("title", e.target.value);
            }}
            error={errors.fields.title}
          />
          {fields.map(([field, label]) => (
            <TextArea
              key={field}
              label={label}
              value={value[field]}
              maxLength={limits.memoryText}
              onChange={(e) => {
                onChange(field, e.target.value);
              }}
              error={errors.fields[field]}
            />
          ))}
        </>
      }
    >
      {fields.map(([field, label]) =>
        value[field] ? (
          <p key={field} className="whitespace-pre-wrap break-words" dir="auto">
            <span className="eyebrow">{label}: </span>
            {value[field]}
          </p>
        ) : null,
      )}
    </ItemFrame>
  );
}
