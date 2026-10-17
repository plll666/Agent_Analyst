import { useEffect, useRef, useState } from 'react'
import type { FormEvent } from 'react'

import { Button } from '../../components/Button'
import { Dialog } from '../../components/Dialog'
import { Field } from '../../components/Field'
import { Input } from '../../components/Input'
import { Textarea } from '../../components/Textarea'
import { toUserMessage } from '../../lib/errors'
import { validateProjectName } from '../../lib/validators'
import type { Project } from '../../types/api'
import { useCreateProject, useUpdateProject } from './useProjectMutations'

export interface ProjectFormDialogProps {
  open: boolean
  project?: Project
  onClose: () => void
}

export function ProjectFormDialog({ open, project, onClose }: ProjectFormDialogProps) {
  const createMutation = useCreateProject()
  const updateMutation = useUpdateProject(project?.id ?? '')
  const nameInputRef = useRef<HTMLInputElement>(null)

  const [name, setName] = useState(project?.name ?? '')
  const [description, setDescription] = useState(project?.description ?? '')
  const [nameError, setNameError] = useState<string | null>(null)

  const isEditing = project !== undefined
  const mutation = isEditing ? updateMutation : createMutation

  useEffect(() => {
    if (open) {
      nameInputRef.current?.focus()
    }
  }, [open])

  useEffect(() => {
    if (open) {
      setName(project?.name ?? '')
      setDescription(project?.description ?? '')
      setNameError(null)
    }
  }, [open, project])

  const handleSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault()

    const trimmedName = name.trim()
    const error = validateProjectName(trimmedName)

    setNameError(error)

    if (error !== null) {
      return
    }

    const payload = {
      name: trimmedName,
      description: description.trim() === '' ? null : description.trim(),
    }

    try {
      await (isEditing ? updateMutation.mutateAsync(payload) : createMutation.mutateAsync(payload))
      onClose()
    } catch {
      return
    }
  }

  return (
    <Dialog
      open={open}
      onClose={onClose}
      title={isEditing ? 'Настройки проекта' : 'Новый проект'}
      description={
        isEditing
          ? 'Название и описание видны только вам'
          : 'Один проект — один анализируемый модуль'
      }
      footer={
        <>
          <Button variant="ghost" onClick={onClose}>
            Отмена
          </Button>
          <Button form="project-form" type="submit" loading={mutation.isPending}>
            {isEditing ? 'Сохранить' : 'Создать проект'}
          </Button>
        </>
      }
    >
      <form
        id="project-form"
        className="space-y-4"
        onSubmit={(event) => void handleSubmit(event)}
        noValidate
      >
        <Field id="project-name" label="Название" error={nameError}>
          <Input
            ref={nameInputRef}
            id="project-name"
            name="projectName"
            type="text"
            placeholder="Модуль заявок"
            value={name}
            invalid={nameError !== null}
            onChange={(event) => setName(event.target.value)}
          />
        </Field>

        <Field id="project-description" label="Описание" hint="Необязательно">
          <Textarea
            id="project-description"
            name="projectDescription"
            rows={3}
            placeholder="Что проверяем и зачем"
            value={description}
            onChange={(event) => setDescription(event.target.value)}
          />
        </Field>

        {mutation.error !== null ? (
          <p role="alert" className="text-sm text-danger">
            {toUserMessage(mutation.error)}
          </p>
        ) : null}
      </form>
    </Dialog>
  )
}
