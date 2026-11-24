import type { ReactNode } from "react";

/**
 * A data table: sunken head row, hairline row rules, its own horizontal scroll. Cells with the
 * `num` class are right-aligned tabular numbers. The caption is read by screen readers; pass
 * `showCaption` to show it as a small heading too.
 */
export function Table({
  caption,
  showCaption = false,
  children,
}: {
  caption: string;
  showCaption?: boolean;
  children: ReactNode;
}) {
  return (
    <div className="overflow-x-auto">
      <table className="w-full border-collapse text-left text-sm [&_.num]:text-right [&_.num]:tabular-nums [&_tbody_tr]:border-t [&_tbody_tr]:border-line [&_td]:px-2 [&_td]:py-1.5 [&_td]:align-top [&_th]:px-2 [&_th]:py-1.5 [&_th]:align-top [&_thead_th]:bg-sunken [&_thead_th]:text-xs [&_thead_th]:font-medium [&_thead_th]:whitespace-nowrap [&_thead_th]:text-muted">
        <caption className={showCaption ? "pb-1 text-left text-base font-medium" : "sr-only"}>
          {caption}
        </caption>
        {children}
      </table>
    </div>
  );
}

/** Label and value pairs, such as a cost estimate. Labels are row headers. */
export function KeyValueTable({ caption, rows }: { caption: string; rows: [string, string][] }) {
  return (
    <table className="w-full border-collapse text-left text-base">
      <caption className="sr-only">{caption}</caption>
      <tbody>
        {rows.map(([k, v]) => (
          <tr key={k} className="border-t border-line first:border-t-0">
            <th scope="row" className="py-1.5 pr-3 font-normal text-muted">
              {k}
            </th>
            <td className="py-1.5 text-right tabular-nums">{v}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}
