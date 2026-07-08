import { ComponentFixture, TestBed } from '@angular/core/testing';

import { CallYourself } from './call-yourself';

describe('CallYourself', () => {
  let component: CallYourself;
  let fixture: ComponentFixture<CallYourself>;

  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [CallYourself]
    })
    .compileComponents();

    fixture = TestBed.createComponent(CallYourself);
    component = fixture.componentInstance;
    fixture.detectChanges();
  });

  it('should create', () => {
    expect(component).toBeTruthy();
  });
});
