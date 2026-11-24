import { act, fireEvent, render, renderHook, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { Inbox } from "lucide-react";
import { useState } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { Button } from "../components/ui/Button";
import { CodeBlock } from "../components/ui/CodeBlock";
import { Dialog } from "../components/ui/Dialog";
import { Badge, Banner, EmptyState, Skeleton } from "../components/ui/Feedback";
import { PageHeader } from "../components/ui/PageHeader";
import { KeyValueTable, Table } from "../components/ui/Table";
import { Tabs } from "../components/ui/Tabs";
import { useTheme } from "../hooks/useTheme";

function DialogHarness({ autofocus = false }: { autofocus?: boolean }) {
  const [open, setOpen] = useState(false);
  return (
    <>
      <button
        type="button"
        onClick={() => {
          setOpen(true);
        }}
      >
        Open
      </button>
      <Dialog
        title="Rename"
        open={open}
        onClose={() => {
          setOpen(false);
        }}
      >
        <label htmlFor="name">Name</label>
        <input id="name" data-autofocus={autofocus || undefined} />
        <button type="button">Save</button>
      </Dialog>
    </>
  );
}

describe("Dialog", () => {
  it("moves focus in, traps Tab, closes on Escape and returns focus", async () => {
    const user = userEvent.setup();
    render(<DialogHarness />);
    const opener = screen.getByRole("button", { name: "Open" });
    await user.click(opener);

    const dialog = screen.getByRole("dialog", { name: "Rename" });
    expect(dialog).toHaveAttribute("aria-modal", "true");
    const close = within(dialog).getByRole("button", { name: "Close" });
    const save = within(dialog).getByRole("button", { name: "Save" });
    expect(close).toHaveFocus();

    await user.tab();
    expect(within(dialog).getByRole("textbox", { name: "Name" })).toHaveFocus();
    await user.tab();
    expect(save).toHaveFocus();
    await user.tab(); // past the last element: back to the first
    expect(close).toHaveFocus();
    await user.tab({ shift: true }); // before the first: to the last
    expect(save).toHaveFocus();

    await user.keyboard("{Escape}");
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(opener).toHaveFocus();
  });

  it("focuses the field marked data-autofocus first", async () => {
    const user = userEvent.setup();
    render(<DialogHarness autofocus />);
    await user.click(screen.getByRole("button", { name: "Open" }));
    expect(screen.getByRole("textbox", { name: "Name" })).toHaveFocus();
  });
});

function TabsHarness() {
  const [tab, setTab] = useState<"a" | "b" | "c">("a");
  return (
    <Tabs
      label="Tools"
      tabs={[
        { id: "a", label: "Memory" },
        { id: "b", label: "Index" },
        { id: "c", label: "Profile" },
      ]}
      active={tab}
      onChange={setTab}
    >
      <p>Panel {tab}</p>
    </Tabs>
  );
}

describe("Tabs", () => {
  it("moves with arrow keys, Home and End, and keeps one tab stop", async () => {
    const user = userEvent.setup();
    render(<TabsHarness />);
    const memory = screen.getByRole("tab", { name: "Memory" });
    const index = screen.getByRole("tab", { name: "Index" });
    const profile = screen.getByRole("tab", { name: "Profile" });
    expect(memory).toHaveAttribute("aria-selected", "true");
    expect(memory).toHaveAttribute("tabindex", "0");
    expect(index).toHaveAttribute("tabindex", "-1");

    await user.tab();
    expect(memory).toHaveFocus();
    await user.keyboard("{ArrowRight}");
    expect(index).toHaveFocus();
    expect(index).toHaveAttribute("aria-selected", "true");
    expect(screen.getByRole("tabpanel", { name: "Index" })).toHaveTextContent("Panel b");

    await user.keyboard("{End}");
    expect(profile).toHaveFocus();
    await user.keyboard("{ArrowRight}"); // wraps
    expect(memory).toHaveFocus();
    await user.keyboard("{ArrowLeft}"); // wraps back
    expect(profile).toHaveFocus();
    await user.keyboard("{Home}");
    expect(memory).toHaveFocus();
    expect(memory).toHaveAttribute("aria-selected", "true");
  });
});

describe("Banner and badges", () => {
  it("announces errors and warnings as alerts, notes as status, with the kind in words", () => {
    render(
      <>
        <Banner kind="danger">The key was refused.</Banner>
        <Banner kind="warning">Re-index needed.</Banner>
        <Banner kind="info">Switched models.</Banner>
        <Banner kind="success">Saved.</Banner>
      </>,
    );
    const alerts = screen.getAllByRole("alert");
    expect(alerts.map((a) => a.textContent)).toEqual([
      "Error:The key was refused.",
      "Warning:Re-index needed.",
    ]);
    const statuses = screen.getAllByRole("status");
    expect(statuses.map((s) => s.textContent)).toEqual(["Note:Switched models.", "Done:Saved."]);
  });

  it("puts the action next to the message", () => {
    render(
      <Banner kind="danger" action={<Button>Retry</Button>}>
        Can&apos;t load.
      </Banner>,
    );
    expect(within(screen.getByRole("alert")).getByRole("button", { name: "Retry" })).toBeVisible();
  });

  it("shows a badge as a word, never colour alone", () => {
    render(<Badge kind="success">works</Badge>);
    expect(screen.getByText("works")).toBeInTheDocument();
  });
});

describe("EmptyState and Skeleton", () => {
  it("says why it is empty and offers one action", async () => {
    const onAdd = vi.fn();
    const user = userEvent.setup();
    render(
      <EmptyState icon={Inbox} action={<Button onClick={onAdd}>Add decision</Button>}>
        No decisions yet.
      </EmptyState>,
    );
    expect(screen.getByText("No decisions yet.")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Add decision" }));
    expect(onAdd).toHaveBeenCalledOnce();
  });

  it("reports loading as a named status", () => {
    render(<Skeleton label="Loading memory" />);
    expect(screen.getByRole("status", { name: "Loading memory" })).toBeInTheDocument();
  });
});

describe("Button", () => {
  it("is disabled and marked busy while a request runs", () => {
    render(<Button busy>Save</Button>);
    const button = screen.getByRole("button", { name: "Save" });
    expect(button).toBeDisabled();
    expect(button).toHaveAttribute("aria-busy", "true");
  });

  it("defaults to type=button so it never submits a form by accident", () => {
    render(<Button>Cancel</Button>);
    expect(screen.getByRole("button", { name: "Cancel" })).toHaveAttribute("type", "button");
  });
});

describe("CodeBlock", () => {
  afterEach(() => {
    vi.useRealTimers();
  });

  it("copies the code without the trailing newline and says so for a moment", async () => {
    vi.useFakeTimers();
    const writeText = vi.fn(() => Promise.resolve());
    Object.defineProperty(navigator, "clipboard", { value: { writeText }, configurable: true });
    render(<CodeBlock>{"npm run build\n"}</CodeBlock>);

    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: "Copy code" }));
      await Promise.resolve();
    });
    expect(writeText).toHaveBeenCalledWith("npm run build");
    expect(screen.getByRole("button", { name: "Copied" })).toBeInTheDocument();

    act(() => {
      vi.advanceTimersByTime(1500);
    });
    expect(screen.getByRole("button", { name: "Copy code" })).toBeInTheDocument();
  });

  it("lays code out left to right", () => {
    render(<CodeBlock>{"x = 1"}</CodeBlock>);
    expect(screen.getByText("x = 1").closest("pre")).toHaveAttribute("dir", "ltr");
  });
});

describe("Table and PageHeader", () => {
  it("names a table by its caption and marks estimate labels as row headers", () => {
    render(
      <>
        <Table caption="Model calls">
          <tbody>
            <tr>
              <td>one</td>
            </tr>
          </tbody>
        </Table>
        <KeyValueTable
          caption="Cost estimate"
          rows={[
            ["Tokens", "1.2k"],
            ["Cost", "$0.01"],
          ]}
        />
      </>,
    );
    expect(screen.getByRole("table", { name: "Model calls" })).toBeInTheDocument();
    const estimate = screen.getByRole("table", { name: "Cost estimate" });
    expect(
      within(estimate)
        .getAllByRole("rowheader")
        .map((h) => h.textContent),
    ).toEqual(["Tokens", "Cost"]);
  });

  it("gives every page one level-one heading", () => {
    render(<PageHeader title="Settings" description="Keys and models." />);
    expect(screen.getAllByRole("heading", { level: 1 })).toHaveLength(1);
  });
});

describe("theme", () => {
  afterEach(() => {
    delete document.documentElement.dataset.theme;
  });

  it("starts light and keeps a saved dark choice", () => {
    const first = renderHook(() => useTheme());
    expect(first.result.current[0]).toBe("light");
    expect(document.documentElement.dataset.theme).toBe("light");
    act(() => {
      first.result.current[1]();
    });
    expect(localStorage.getItem("mantle.theme")).toBe("dark");
    first.unmount();

    const second = renderHook(() => useTheme());
    expect(second.result.current[0]).toBe("dark");
  });
});
