import { Meta, StoryObj } from "@storybook/react";

import SensitiveDataForm from "src/sensitiveData/components/sensitiveDataForm/SensitiveDataForm";
import UserPreferencesStateService from "src/userPreferences/UserPreferencesStateService";
import {
  Language,
  SensitivePersonalDataRequirement,
} from "src/userPreferences/UserPreferencesService/userPreferences.types";
import { getBackendUrl } from "src/envService";
import InstitutionService from "src/institutions/services/InstitutionService";
import { faker } from "@faker-js/faker";

const SAMPLE_PROVINCES = ["Central", "Eastern", "Northern", "Southern", "Western"];
const INSTITUTION_TYPES = ["University", "College", "Polytechnic", "Technical Institute"];
const SECTOR_POOL = ["Engineering", "ICT", "Business", "Health", "Education", "Hospitality", "Agriculture", "Mining"];

const SAMPLE_INSTITUTIONS = Array.from({ length: 5 }, (_, i) => ({
  name: `${faker.location.city()} ${faker.helpers.arrayElement(INSTITUTION_TYPES)}`,
  reg_no: `REG${String(i + 1).padStart(3, "0")}`,
  province: faker.helpers.arrayElement(SAMPLE_PROVINCES),
  sectors_covered: faker.helpers.arrayElements(SECTOR_POOL, { min: 1, max: 2 }),
}));

const mockInstitutionService = () => {
  const service = InstitutionService.getInstance();
  const original = {
    searchInstitutions: service.searchInstitutions,
    getInstitutionAssignment: service.getInstitutionAssignment,
    getProgrammesByInstitution: service.getProgrammesByInstitution,
  };

  service.searchInstitutions = async () => ({
    data: SAMPLE_INSTITUTIONS,
    meta: { limit: 500, has_more: false, next_cursor: null, total: SAMPLE_INSTITUTIONS.length },
  });
  service.getInstitutionAssignment = async () => null;
  service.getProgrammesByInstitution = async (regNo: string) => ({
    name: SAMPLE_INSTITUTIONS.find((institution) => institution.reg_no === regNo)?.name ?? "",
    reg_no: regNo,
    programmes: [
      { name: "Computer Science", qualification_type: "BSc", zqf_level: "7", sectors: ["ICT"] },
      { name: "Civil Engineering", qualification_type: "BEng", zqf_level: "7", sectors: ["Engineering"] },
    ],
  });

  return () => {
    service.searchInstitutions = original.searchInstitutions;
    service.getInstitutionAssignment = original.getInstitutionAssignment;
    service.getProgrammesByInstitution = original.getProgrammesByInstitution;
  };
};

const meta: Meta<typeof SensitiveDataForm> = {
  title: "SensitiveData/SensitiveDataForm",
  component: SensitiveDataForm,
  tags: ["autodocs"],
  parameters: {
    mockData: [
      {
        url: `${getBackendUrl()}/users/foo/sensitive-personal-data`,
        method: "POST",
        status: 201,
        response: {
          data: "",
        },
      },
    ],
  },
};

export default meta;

export const Shown: StoryObj<typeof SensitiveDataForm> = {
  beforeEach: () => {
    UserPreferencesStateService.getInstance().setUserPreferences({
      user_id: "foo",
      has_sensitive_personal_data: false,
      accepted_tc: new Date(),
      sessions: [],
      sensitive_personal_data_requirement: SensitivePersonalDataRequirement.REQUIRED,
      user_feedback_answered_questions: {},
      language: Language.en,
      experiments: {},
    });
    const restoreInstitutionService = mockInstitutionService();
    return () => {
      UserPreferencesStateService.getInstance().clearUserPreferences();
      restoreInstitutionService();
    };
  },
  args: {},
};

export const ShownWhenSkipping: StoryObj<typeof SensitiveDataForm> = {
  beforeEach: () => {
    UserPreferencesStateService.getInstance().setUserPreferences({
      user_id: "foo",
      has_sensitive_personal_data: false,
      accepted_tc: new Date(),
      sessions: [],
      sensitive_personal_data_requirement: SensitivePersonalDataRequirement.NOT_REQUIRED,
      user_feedback_answered_questions: {},
      language: Language.en,
      experiments: {},
    });
    const restoreInstitutionService = mockInstitutionService();
    return () => {
      UserPreferencesStateService.getInstance().clearUserPreferences();
      restoreInstitutionService();
    };
  },
  args: {},
};
