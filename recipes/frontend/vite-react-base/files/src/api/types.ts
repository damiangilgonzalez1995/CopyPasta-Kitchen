/** Shapes exchanged with the backend. Keep them in sync with the backend schemas (Pydantic models). */

export type Identity = {
  userId: string
  tenantId: string
  name: string
}
