import { CircleAlert } from "lucide-react";
import {
  useId,
  type InputHTMLAttributes,
  type ReactNode,
  type SelectHTMLAttributes,
  type TextareaHTMLAttributes,
} from "react";

/** The look of every text input and select (docs/design-app.md, "Inputs"). */
export const CONTROL =
  "w-full rounded-sm border border-field bg-paper px-2 text-base text-text transition-colors duration-150 ease-out hover:border-text focus:border-text disabled:cursor-not-allowed disabled:opacity-50 aria-[invalid=true]:border-danger";

interface FieldProps {
  label: string;
  error?: string | undefined;
  help?: ReactNode;
  children: (ids: { id: string; describedBy: string | undefined; invalid: boolean }) => ReactNode;
}

/** Label above, help and error under the control, linked with aria-describedby. */
export function Field({ label, error, help, children }: FieldProps) {
  const id = useId();
  const helpId = `${id}-help`;
  const errorId = `${id}-error`;
  const describedBy = [help ? helpId : null, error ? errorId : null].filter(Boolean).join(" ");
  return (
    <div className="flex flex-col gap-1">
      <label htmlFor={id} className="text-sm text-text">
        {label}
      </label>
      {children({ id, describedBy: describedBy || undefined, invalid: Boolean(error) })}
      {help ? (
        <p id={helpId} className="text-sm text-muted">
          {help}
        </p>
      ) : null}
      {error ? (
        <p id={errorId} role="alert" className="flex items-center gap-1 text-sm text-danger">
          <CircleAlert aria-hidden className="size-4 shrink-0" />
          {error}
        </p>
      ) : null}
    </div>
  );
}

type Shared = { label: string; error?: string | undefined; help?: ReactNode };

export function TextInput({
  label,
  error,
  help,
  ...rest
}: Shared & InputHTMLAttributes<HTMLInputElement>) {
  return (
    <Field label={label} error={error} help={help}>
      {({ id, describedBy, invalid }) => (
        <input
          id={id}
          aria-describedby={describedBy}
          aria-invalid={invalid}
          className={`${CONTROL} h-8`}
          {...rest}
        />
      )}
    </Field>
  );
}

export function TextArea({
  label,
  error,
  help,
  ...rest
}: Shared & TextareaHTMLAttributes<HTMLTextAreaElement>) {
  return (
    <Field label={label} error={error} help={help}>
      {({ id, describedBy, invalid }) => (
        <textarea
          id={id}
          aria-describedby={describedBy}
          aria-invalid={invalid}
          className={`${CONTROL} min-h-20 py-1.5`}
          dir="auto"
          {...rest}
        />
      )}
    </Field>
  );
}

export function SelectInput({
  label,
  error,
  help,
  children,
  ...rest
}: Shared & SelectHTMLAttributes<HTMLSelectElement>) {
  return (
    <Field label={label} error={error} help={help}>
      {({ id, describedBy, invalid }) => (
        <select
          id={id}
          aria-describedby={describedBy}
          aria-invalid={invalid}
          className={`${CONTROL} h-8`}
          {...rest}
        >
          {children}
        </select>
      )}
    </Field>
  );
}

export function Checkbox({
  label,
  help,
  ...rest
}: { label: string; help?: ReactNode } & InputHTMLAttributes<HTMLInputElement>) {
  const id = useId();
  return (
    <div className="flex items-start gap-2">
      <input id={id} type="checkbox" className="mt-0.5 size-4 shrink-0 accent-accent" {...rest} />
      <div>
        <label htmlFor={id} className="text-base font-normal">
          {label}
        </label>
        {help ? <p className="text-sm text-muted">{help}</p> : null}
      </div>
    </div>
  );
}

/** A form-level error (not tied to one field), shown above the submit button. */
export function FormError({ message }: { message: string | null | undefined }) {
  if (!message) return null;
  return (
    <p role="alert" className="flex items-center gap-1 text-sm text-danger">
      <CircleAlert aria-hidden className="size-4 shrink-0" />
      {message}
    </p>
  );
}
