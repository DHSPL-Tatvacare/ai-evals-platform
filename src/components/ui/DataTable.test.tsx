import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { DataTable, type ColumnDef } from './DataTable';

interface Row {
  id: string;
  name: string;
}

const rows: Row[] = [{ id: '1', name: 'Alpha' }];

function renderTable(onRowClick: (r: Row) => void) {
  const columns: ColumnDef<Row>[] = [
    { key: 'name', header: 'Name', render: (r) => <span>{r.name}</span> },
    {
      key: 'action',
      header: 'Action',
      render: () => <button type="button">Edit</button>,
    },
    {
      key: 'opt-out',
      header: 'Custom',
      render: () => (
        <span data-row-click-ignore>
          <span>noop</span>
        </span>
      ),
    },
  ];
  render(
    <DataTable
      columns={columns}
      data={rows}
      keyExtractor={(r) => r.id}
      onRowClick={onRowClick}
    />,
  );
}

describe('DataTable row click guard', () => {
  it('fires onRowClick when a plain cell is clicked', () => {
    const onRowClick = vi.fn();
    renderTable(onRowClick);
    fireEvent.click(screen.getByText('Alpha'));
    expect(onRowClick).toHaveBeenCalledTimes(1);
  });

  it('does NOT fire onRowClick when an interactive control in the row is clicked', () => {
    const onRowClick = vi.fn();
    renderTable(onRowClick);
    fireEvent.click(screen.getByRole('button', { name: 'Edit' }));
    expect(onRowClick).not.toHaveBeenCalled();
  });

  it('does NOT fire onRowClick when a [data-row-click-ignore] container is clicked', () => {
    const onRowClick = vi.fn();
    renderTable(onRowClick);
    fireEvent.click(screen.getByText('noop'));
    expect(onRowClick).not.toHaveBeenCalled();
  });
});
