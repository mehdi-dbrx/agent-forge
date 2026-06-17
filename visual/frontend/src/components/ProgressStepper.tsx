interface ProgressStepperProps {
  stages: string[]
  currentStage: number
}

export function ProgressStepper({ stages, currentStage }: ProgressStepperProps) {
  return (
    <div className="flex flex-col gap-0 px-1 py-2 font-mono text-[10px]">
      {stages.map((label, i) => (
        <div key={label} className="flex items-center gap-2">
          <div className="flex flex-col items-center w-3">
            <div className={`w-2 h-2 rounded-full flex-shrink-0 ${
              i < currentStage ? 'bg-dbx-blue dark:bg-dbx-green' :
              i === currentStage ? 'bg-dbx-amber animate-pulse' :
              'bg-dbx-gray-300 dark:bg-dbx-gray-700'
            }`} />
            {i < stages.length - 1 && (
              <div className={`w-px h-3 ${i < currentStage ? 'bg-dbx-blue dark:bg-dbx-green' : 'bg-dbx-gray-300 dark:bg-dbx-gray-700'}`} />
            )}
          </div>
          <span className={
            i < currentStage ? 'text-dbx-green' :
            i === currentStage ? 'text-dbx-amber' :
            'text-dbx-gray-400 dark:text-dbx-gray-600'
          }>{label}</span>
        </div>
      ))}
    </div>
  )
}
