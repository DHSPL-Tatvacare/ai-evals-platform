import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('@/services/api/orchestrationDatasets', () => ({
  orchestrationDatasetsApi: {
    uploadVersion: vi.fn(),
    formats: vi.fn().mockResolvedValue([
      {
        sourceType: 'csv',
        extensions: ['.csv'],
        mimeTypes: ['text/csv'],
        label: 'CSV (.csv)',
        maxUploadBytes: 50 * 1024 * 1024,
        supportsClientPreview: true,
      },
      {
        sourceType: 'xlsx',
        extensions: ['.xlsx'],
        mimeTypes: [
          'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        ],
        label: 'Excel (.xlsx)',
        maxUploadBytes: 50 * 1024 * 1024,
        supportsClientPreview: true,
      },
    ]),
  },
}));

vi.mock('@/services/notifications', () => ({
  notificationService: {
    success: vi.fn(),
    error: vi.fn(),
    info: vi.fn(),
    warning: vi.fn(),
  },
}));

import { ApiError } from '@/services/api/client';
import { orchestrationDatasetsApi } from '@/services/api/orchestrationDatasets';
import { DatasetUploadForm } from '@/features/orchestration/components/datasets/DatasetUploadForm';

function renderForm(
  overrides: Partial<React.ComponentProps<typeof DatasetUploadForm>> = {},
) {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <QueryClientProvider client={qc}>
      <DatasetUploadForm
        datasetId="ds-1"
        onClose={() => {}}
        onUploaded={() => {}}
        {...overrides}
      />
    </QueryClientProvider>,
  );
}

function csvFile(content: string, name = 'cohort.csv'): File {
  return new File([content], name, { type: 'text/csv' });
}

async function waitForDropZone() {
  await waitFor(() =>
    expect(screen.getByLabelText('Data file')).toBeInTheDocument(),
  );
}

/** Selects a file in step 1 and waits for the data preview to appear. */
async function pickFile(file: File) {
  await waitForDropZone();
  const input = screen.getByLabelText('Data file') as HTMLInputElement;
  fireEvent.change(input, { target: { files: [file] } });
  await waitFor(() =>
    expect(screen.getByText('Data Preview')).toBeInTheDocument(),
  );
}

/** Advances from step 1 (upload) to step 2 (configure recipients). */
function goToConfigure() {
  fireEvent.click(screen.getByRole('button', { name: 'Next' }));
}

/**
 * Drives the required "Contact column" Select on step 2, the same way the
 * recipient-ID column Select is driven: open the combobox, click the option.
 * Both Selects share the "Select a column" placeholder, but the recipient-ID
 * Select is hidden under the UUID strategy, so the combobox is unambiguous.
 */
async function pickContactColumn(column: string) {
  const user = userEvent.setup();
  await user.click(screen.getByRole('combobox', { name: 'Select a column' }));
  await user.click(await screen.findByRole('option', { name: column }));
}

describe('DatasetUploadForm', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders the drop zone and step-1 footer initially', async () => {
    renderForm();
    await waitForDropZone();
    expect(screen.getByText(/Step 1 of 2/)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Next' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Cancel' })).toBeInTheDocument();
    expect(screen.getByText(/Supported: .csv, .xlsx/)).toBeInTheDocument();
  });

  it('shows a data preview for a selected CSV and enables Next', async () => {
    renderForm();
    const next = screen.getByRole('button', { name: 'Next' });
    expect(next).toBeDisabled();

    await pickFile(csvFile('phone,name\n+91111,Alice\n+91222,Bob\n'));

    expect(screen.getByText('phone')).toBeInTheDocument();
    expect(screen.getByText('name')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Next' })).not.toBeDisabled();
  });

  it('blocks Next on an interior blank header', async () => {
    renderForm();
    await waitForDropZone();
    const input = screen.getByLabelText('Data file') as HTMLInputElement;
    fireEvent.change(input, {
      target: { files: [csvFile('phone,,name\n+91111,x,Alice\n')] },
    });

    expect(
      await screen.findByText(/Blank column header/),
    ).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Next' })).toBeDisabled();
  });

  it('blocks Next on a duplicate header', async () => {
    renderForm();
    await waitForDropZone();
    const input = screen.getByLabelText('Data file') as HTMLInputElement;
    fireEvent.change(input, {
      target: { files: [csvFile('phone,phone\n+91111,+91222\n')] },
    });

    expect(
      await screen.findByText(/Duplicate column header/),
    ).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Next' })).toBeDisabled();
  });

  it('on step 2, disables upload until a column is chosen for column-strategy', async () => {
    renderForm();
    await pickFile(csvFile('phone,name\n+91111,Alice\n'));
    goToConfigure();

    expect(screen.getByText(/Step 2 of 2/)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Upload version' })).toBeDisabled();
  });

  it('switching to UUID strategy hides the column dropdown and enables upload', async () => {
    renderForm();
    await pickFile(csvFile('phone,name\n+91111,Alice\n'));
    goToConfigure();

    fireEvent.click(screen.getByLabelText(/Auto-generate IDs/));
    expect(screen.queryByText('Recipient ID')).not.toBeInTheDocument();
    await pickContactColumn('phone');
    expect(
      screen.getByRole('button', { name: 'Upload version' }),
    ).not.toBeDisabled();
  });

  it('calls uploadVersion with the right args on submit (uuid strategy)', async () => {
    (orchestrationDatasetsApi.uploadVersion as ReturnType<typeof vi.fn>).mockResolvedValue({
      id: 'ver-1',
      datasetId: 'ds-1',
      versionNumber: 1,
      sourceType: 'csv',
      sourceFilename: 'cohort.csv',
      sourceByteSize: 100,
      rowCount: 1,
      idStrategy: 'uuid',
      idColumn: null,
      schemaDescriptor: { columns: [], rowCount: 1 },
      importedBy: 'u',
      importedAt: '2026-05-03T00:00:00Z',
    });
    const onUploaded = vi.fn();
    renderForm({ onUploaded });
    const file = csvFile('phone,name\n+91111,Alice\n');
    await pickFile(file);
    goToConfigure();

    fireEvent.click(screen.getByLabelText(/Auto-generate IDs/));
    await pickContactColumn('phone');
    fireEvent.click(screen.getByRole('button', { name: 'Upload version' }));

    await waitFor(() =>
      expect(orchestrationDatasetsApi.uploadVersion).toHaveBeenCalledWith(
        'ds-1',
        file,
        'uuid',
        undefined,
        'phone',
      ),
    );
    await waitFor(() => expect(onUploaded).toHaveBeenCalledTimes(1));
  });

  it('renders server-side 400 errors without leaving step 2', async () => {
    (orchestrationDatasetsApi.uploadVersion as ReturnType<typeof vi.fn>).mockRejectedValue(
      new ApiError(400, 'Invalid id_column "foo": not present in header row'),
    );
    renderForm();
    await pickFile(csvFile('phone,name\n+91111,Alice\n'));
    goToConfigure();

    fireEvent.click(screen.getByLabelText(/Auto-generate IDs/));
    await pickContactColumn('phone');
    fireEvent.click(screen.getByRole('button', { name: 'Upload version' }));

    expect(
      await screen.findByText(/Invalid id_column "foo"/),
    ).toBeInTheDocument();
    expect(screen.getByText(/Step 2 of 2/)).toBeInTheDocument();
  });

  it('rejects an unsupported file extension in step 1', async () => {
    renderForm();
    await waitForDropZone();
    const input = screen.getByLabelText('Data file') as HTMLInputElement;
    const pdf = new File(['x'], 'leads.pdf', { type: 'application/pdf' });
    fireEvent.change(input, { target: { files: [pdf] } });
    expect(
      await screen.findByText(/Unsupported file type/),
    ).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Next' })).toBeDisabled();
  });
});
